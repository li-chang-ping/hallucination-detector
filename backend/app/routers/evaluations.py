import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DetectionItem, DetectionTask, Evaluation
from app.schemas.evaluations import EvaluationRead, GroundTruthItem
from app.services.evaluations import calculate_metrics

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/tasks/{task_id}", response_model=list[EvaluationRead])
def list_evaluations(task_id: str, session: DbSession) -> list[Evaluation]:
    return list(
        session.scalars(
            select(Evaluation)
            .where(Evaluation.task_id == task_id)
            .order_by(Evaluation.created_at.desc())
        )
    )


@router.post(
    "/tasks/{task_id}", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED
)
async def evaluate_task(
    task_id: str, session: DbSession, file: Annotated[UploadFile, File()]
) -> Evaluation:
    if session.get(DetectionTask, task_id) is None:
        raise HTTPException(status_code=404, detail="检测任务不存在")
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 JSON 文件")
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
        truths = TypeAdapter(list[GroundTruthItem]).validate_python(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"人工标注 JSON 格式错误: {exc}") from exc
    predictions = list(
        session.scalars(select(DetectionItem).where(DetectionItem.task_id == task_id))
    )
    evaluation = Evaluation(
        task_id=task_id,
        metrics=calculate_metrics(predictions, truths),
        ground_truth_count=len(truths),
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    return evaluation

