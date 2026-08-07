import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.models import Category, DetectionItem, DetectionTask, KnowledgeBase, TaskStatus, utc_now
from app.schemas.tasks import DetectionTaskDetail, DetectionTaskRead, ReplyBatch, ReplyInput
from app.services.task_runner import TaskRunner, get_task_runner

router = APIRouter(prefix="/tasks", tags=["tasks"])
DbSession = Annotated[Session, Depends(get_db)]
Runner = Annotated[TaskRunner, Depends(get_task_runner)]


def task_or_404(session: Session, task_id: str, details: bool = False) -> DetectionTask:
    statement = select(DetectionTask).where(DetectionTask.id == task_id)
    if details:
        statement = statement.options(selectinload(DetectionTask.items))
    task = session.scalar(statement)
    if task is None:
        raise HTTPException(status_code=404, detail="检测任务不存在")
    return task


@router.get("", response_model=list[DetectionTaskRead])
def list_tasks(session: DbSession) -> list[DetectionTask]:
    return list(session.scalars(select(DetectionTask).order_by(DetectionTask.created_at.desc())))


@router.get("/{task_id}", response_model=DetectionTaskDetail)
def get_task(task_id: str, session: DbSession) -> DetectionTask:
    return task_or_404(session, task_id, details=True)


@router.post("", response_model=DetectionTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    session: DbSession,
    runner: Runner,
    name: Annotated[str, Form(min_length=2, max_length=120)],
    knowledge_base_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> DetectionTask:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=503, detail="请先配置 DEEPSEEK_API_KEY")
    if session.get(KnowledgeBase, knowledge_base_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 JSON 文件")
    try:
        raw = json.loads((await file.read()).decode("utf-8"))
        replies = ReplyBatch(items=TypeAdapter(list[ReplyInput]).validate_python(raw)).items
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"回复 JSON 格式错误: {exc}") from exc
    categories = list(
        session.scalars(
            select(Category).where(Category.is_active.is_(True), Category.is_archived.is_(False))
        )
    )
    if not categories:
        raise HTTPException(status_code=409, detail="至少需要一个启用的幻觉分类")
    snapshot = [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "default_severity": item.default_severity,
            "prompt_guidance": item.prompt_guidance,
        }
        for item in categories
    ]
    task = DetectionTask(
        name=name,
        knowledge_base_id=knowledge_base_id,
        status=TaskStatus.QUEUED,
        model_name=settings.deepseek_model,
        total_count=len(replies),
        category_snapshot=snapshot,
    )
    session.add(task)
    session.flush()
    session.add_all(
        [
            DetectionItem(
                task_id=task.id,
                input_id=item.id,
                position=index,
                user_question=item.user_question,
                system_reply=item.system_reply,
            )
            for index, item in enumerate(replies)
        ]
    )
    session.commit()
    session.refresh(task)
    runner.start(task.id)
    return task


@router.post("/{task_id}/pause", response_model=DetectionTaskRead)
def pause_task(task_id: str, session: DbSession) -> DetectionTask:
    task = task_or_404(session, task_id)
    if task.status not in {TaskStatus.PREPARING, TaskStatus.QUEUED, TaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="当前状态不能暂停")
    task.status = TaskStatus.PAUSED
    task.updated_at = utc_now()
    session.commit()
    return task


@router.post("/{task_id}/resume", response_model=DetectionTaskRead)
def resume_task(task_id: str, session: DbSession, runner: Runner) -> DetectionTask:
    task = task_or_404(session, task_id)
    if task.status != TaskStatus.PAUSED:
        raise HTTPException(status_code=409, detail="仅暂停任务可以继续")
    session.query(DetectionItem).filter(
        DetectionItem.task_id == task_id, DetectionItem.status == "running"
    ).update({"status": "pending"})
    task.status = TaskStatus.QUEUED
    task.updated_at = utc_now()
    session.commit()
    runner.start(task.id)
    return task


@router.post("/{task_id}/cancel", response_model=DetectionTaskRead)
def cancel_task(task_id: str, session: DbSession) -> DetectionTask:
    task = task_or_404(session, task_id)
    if task.status in {TaskStatus.COMPLETED, TaskStatus.PARTIAL, TaskStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="当前状态不能取消")
    task.status = TaskStatus.CANCELLED
    task.finished_at = utc_now()
    task.updated_at = utc_now()
    session.commit()
    return task
