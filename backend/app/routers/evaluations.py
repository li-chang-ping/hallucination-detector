import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models import CategorySuggestion, DetectionItem, DetectionTask, Evaluation, TaskStatus
from app.schemas.evaluations import (
    CategorySuggestionRead,
    EvaluationRead,
    GroundTruthBatch,
    GroundTruthItem,
)
from app.services.evaluations import (
    calculate_metrics,
    decide_suggestion,
    decide_suggestion_plan,
    record_evaluation_progress,
    run_evaluation_insights,
    validate_ground_truth_ids,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
DbSession = Annotated[Session, Depends(get_db)]


def evaluation_or_404(session: Session, evaluation_id: str) -> Evaluation:
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="人工评测不存在")
    return evaluation


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
    "/tasks/{task_id}", response_model=EvaluationRead, status_code=status.HTTP_202_ACCEPTED
)
async def evaluate_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> Evaluation:
    task = session.get(DetectionTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="检测任务不存在")
    if task.status not in {
        TaskStatus.COMPLETED,
        TaskStatus.PARTIAL,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }:
        raise HTTPException(status_code=409, detail="检测任务尚未结束，暂不能上传人工标注")
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 JSON 文件")
    try:
        payload = json.loads((await file.read()).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"人工标注 JSON 无法解析: {exc}") from exc
    if not isinstance(payload, list):
        raise HTTPException(status_code=422, detail="人工标注 JSON 顶层必须是数组")
    if payload and isinstance(payload[0], dict) and "is_hallucination" not in payload[0]:
        if "user_question" in payload[0] or "system_reply" in payload[0]:
            raise HTTPException(
                status_code=422,
                detail=(
                    "上传的是检测回复数据，不是人工标注结果；"
                    "请上传每条包含 id、is_hallucination、hallucination_type 和 detail 的 JSON"
                ),
            )
        raise HTTPException(
            status_code=422,
            detail="人工标注第 1 条缺少必填字段 is_hallucination",
        )
    try:
        truths = GroundTruthBatch(
            items=TypeAdapter(list[GroundTruthItem]).validate_python(payload)
        ).items
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first_error.get("loc", ()))
        message = str(first_error.get("msg", "字段格式不正确"))
        detail = f"人工标注字段 {location or '未知'} 格式错误：{message}"
        raise HTTPException(status_code=422, detail=detail) from exc
    predictions = list(
        session.scalars(select(DetectionItem).where(DetectionItem.task_id == task_id))
    )
    try:
        validate_ground_truth_ids(predictions, truths)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    evaluation = Evaluation(
        task_id=task_id,
        metrics=calculate_metrics(predictions, truths),
        ground_truth_count=len(truths),
        insight_status="pending",
        insight_progress=10,
        insight_stage="人工标注校验完成，等待后台分析",
        ground_truth_snapshot=[item.model_dump(mode="json") for item in truths],
    )
    session.add(evaluation)
    session.flush()
    record_evaluation_progress(
        session,
        evaluation,
        "人工标注校验完成，已创建后台评测",
        10,
        status="pending",
    )
    session.refresh(evaluation)
    background_tasks.add_task(run_evaluation_insights, evaluation.id)
    return evaluation


@router.get("/{evaluation_id}/events")
async def stream_evaluation_events(
    evaluation_id: str, request: Request, session: DbSession
) -> StreamingResponse:
    evaluation_or_404(session, evaluation_id)

    async def event_stream() -> AsyncIterator[str]:
        cursor = 0
        while True:
            if await request.is_disconnected():
                return
            with SessionLocal() as event_session:
                current = event_session.get(Evaluation, evaluation_id)
                if current is None:
                    payload = {"status": "failed", "stage": "人工评测不存在", "progress": 100}
                    yield f"event: failed\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
                events = list(current.insight_events or [])
                current_status = current.insight_status
            for event in events[cursor:]:
                cursor += 1
                yield (
                    f"id: {event.get('sequence', cursor)}\n"
                    f"event: progress\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
            if current_status in {"completed", "fallback"} and cursor >= len(events):
                yield (
                    "event: complete\n"
                    f"data: {json.dumps({'status': current_status}, ensure_ascii=False)}\n\n"
                )
                return
            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@router.post(
    "/{evaluation_id}/suggestions/apply-all",
    response_model=list[CategorySuggestionRead],
)
def apply_suggestion_plan(evaluation_id: str, session: DbSession) -> list[CategorySuggestion]:
    try:
        return decide_suggestion_plan(
            session, evaluation_or_404(session, evaluation_id), apply=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="优化方案存在分类名称冲突，已全部回滚") from exc


@router.post(
    "/{evaluation_id}/suggestions/reject-all",
    response_model=list[CategorySuggestionRead],
)
def reject_suggestion_plan(evaluation_id: str, session: DbSession) -> list[CategorySuggestion]:
    try:
        return decide_suggestion_plan(
            session, evaluation_or_404(session, evaluation_id), apply=False
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
