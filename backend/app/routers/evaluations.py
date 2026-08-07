import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CategorySuggestion, DetectionItem, DetectionTask, Evaluation
from app.schemas.evaluations import CategorySuggestionRead, EvaluationRead, GroundTruthItem
from app.services.evaluations import (
    calculate_metrics,
    create_evaluation_insights,
    decide_suggestion,
)

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


@router.post("/tasks/{task_id}", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED)
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
    await create_evaluation_insights(session, evaluation, predictions, truths)
    session.refresh(evaluation)
    return evaluation


@router.post(
    "/{evaluation_id}/suggestions/{suggestion_id}/apply", response_model=CategorySuggestionRead
)
def apply_suggestion(
    evaluation_id: str, suggestion_id: str, session: DbSession
) -> CategorySuggestion:
    suggestion = session.get(CategorySuggestion, suggestion_id)
    if suggestion is None or suggestion.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404, detail="优化建议不存在")
    try:
        return decide_suggestion(session, suggestion, apply=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="建议中的分类名称已存在") from exc


@router.post(
    "/{evaluation_id}/suggestions/{suggestion_id}/reject", response_model=CategorySuggestionRead
)
def reject_suggestion(
    evaluation_id: str, suggestion_id: str, session: DbSession
) -> CategorySuggestion:
    suggestion = session.get(CategorySuggestion, suggestion_id)
    if suggestion is None or suggestion.evaluation_id != evaluation_id:
        raise HTTPException(status_code=404, detail="优化建议不存在")
    try:
        return decide_suggestion(session, suggestion, apply=False)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
