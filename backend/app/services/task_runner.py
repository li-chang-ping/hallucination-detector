import asyncio
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DetectionItem, DetectionTask, TaskStatus, utc_now
from app.schemas.tasks import DetectionDecision
from app.services.deepseek import DeepSeekClient
from app.services.vector_store import get_vector_store


class TaskRunner:
    """Cooperative in-process runner; checkpoints every item in SQLite."""

    def __init__(self) -> None:
        self.running: dict[str, asyncio.Task[None]] = {}

    def start(self, task_id: str) -> None:
        current = self.running.get(task_id)
        if current is None or current.done():
            self.running[task_id] = asyncio.create_task(self._run(task_id))

    async def _run(self, task_id: str) -> None:
        try:
            await self._prepare(task_id)
            await self._detect(task_id)
        finally:
            self.running.pop(task_id, None)

    async def _prepare(self, task_id: str) -> None:
        with SessionLocal() as session:
            task = session.get(DetectionTask, task_id)
            if task is None or task.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED}:
                return
            task.status = TaskStatus.PREPARING
            task.updated_at = utc_now()
            session.commit()
            items = list(
                session.scalars(
                    select(DetectionItem)
                    .where(DetectionItem.task_id == task_id, DetectionItem.status == "pending")
                    .order_by(DetectionItem.position)
                )
            )
            kb_id = task.knowledge_base_id
            if kb_id is None:
                raise RuntimeError("检测任务引用的知识库已不存在")
        vectors = get_vector_store()
        for item in items:
            with SessionLocal() as session:
                task = session.get(DetectionTask, task_id)
                if task is None or task.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED}:
                    return
            query = f"用户问题：{item.user_question}\n客服回复：{item.system_reply}"
            evidence = await asyncio.to_thread(vectors.query, kb_id, query, 5)
            with SessionLocal() as session:
                stored = session.get(DetectionItem, item.id)
                if stored is not None:
                    stored.evidence_snapshot = evidence
                    session.commit()
        with SessionLocal() as session:
            task = session.get(DetectionTask, task_id)
            if task is not None and task.status == TaskStatus.PREPARING:
                task.status = TaskStatus.RUNNING
                task.started_at = task.started_at or utc_now()
                task.updated_at = utc_now()
                session.commit()

    async def _detect(self, task_id: str) -> None:
        client = DeepSeekClient()
        while True:
            with SessionLocal() as session:
                task = session.get(DetectionTask, task_id)
                if task is None or task.status != TaskStatus.RUNNING:
                    return
                item = session.scalar(
                    select(DetectionItem)
                    .where(DetectionItem.task_id == task_id, DetectionItem.status == "pending")
                    .order_by(DetectionItem.position)
                    .limit(1)
                )
                if item is None:
                    self._finish(session, task)
                    return
                item.status = "running"
                session.commit()
                question = item.user_question
                reply = item.system_reply
                evidence = item.evidence_snapshot
                categories = task.category_snapshot
                item_id = item.id
            try:
                decision, usage = await client.detect(question, reply, evidence, categories)
                self._save_success(item_id, decision, usage)
            except Exception as exc:
                self._save_error(item_id, str(exc))

    @staticmethod
    def _save_success(item_id: str, decision: DetectionDecision, usage: dict[str, int]) -> None:
        with SessionLocal() as session:
            item = session.get(DetectionItem, item_id)
            if item is None:
                return
            item.status = "completed"
            item.is_hallucination = decision.is_hallucination
            item.category_names = decision.category_names
            item.primary_category = decision.primary_category
            item.severity = decision.severity.value if decision.severity else None
            item.confidence = decision.confidence
            item.rationale = decision.rationale
            item.prompt_tokens = usage["prompt_tokens"]
            item.completion_tokens = usage["completion_tokens"]
            task = item.task
            task.completed_count += 1
            task.updated_at = utc_now()
            session.commit()

    @staticmethod
    def _save_error(item_id: str, message: str) -> None:
        with SessionLocal() as session:
            item = session.get(DetectionItem, item_id)
            if item is None:
                return
            item.status = "failed"
            item.error_message = message[:2000]
            item.task.error_count += 1
            item.task.updated_at = utc_now()
            session.commit()

    @staticmethod
    def _finish(session: Session, task: DetectionTask) -> None:
        task.status = TaskStatus.PARTIAL if task.error_count else TaskStatus.COMPLETED
        task.finished_at = utc_now()
        task.updated_at = utc_now()
        session.commit()


@lru_cache
def get_task_runner() -> TaskRunner:
    return TaskRunner()


def recover_interrupted_tasks() -> None:
    with SessionLocal() as session:
        tasks = session.scalars(
            select(DetectionTask).where(
                DetectionTask.status.in_(
                    [TaskStatus.PREPARING, TaskStatus.QUEUED, TaskStatus.RUNNING]
                )
            )
        )
        for task in tasks:
            task.status = TaskStatus.PAUSED
            task.updated_at = utc_now()
        session.commit()
