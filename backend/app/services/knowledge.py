from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DetectionTask, KnowledgeBase, KnowledgeEntry, TaskStatus, utc_now
from app.schemas.knowledge import KnowledgeEntryCreate, KnowledgeEntryUpdate, KnowledgeImport


class VectorStoreProtocol(Protocol):
    def upsert(
        self,
        knowledge_base_id: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, object]],
    ) -> None: ...

    def delete_entry(self, knowledge_base_id: str, entry_id: str) -> None: ...
    def delete_knowledge_base(self, knowledge_base_id: str) -> None: ...


class KnowledgeBaseInUseError(RuntimeError):
    pass


class KnowledgeEntryConflictError(RuntimeError):
    pass


NON_TERMINAL_TASK_STATUSES = {
    TaskStatus.PREPARING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.PAUSED,
}


def import_knowledge_base(
    session: Session, data: KnowledgeImport, vectors: VectorStoreProtocol
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        name=data.name,
        description=data.description,
        embedding_model=get_settings().ollama_embed_model,
    )
    session.add(knowledge_base)
    session.flush()
    entries = [
        KnowledgeEntry(
            external_id=item.id,
            knowledge_base_id=knowledge_base.id,
            title=item.title,
            content=item.content,
            extra_metadata=item.metadata,
        )
        for item in data.entries
    ]
    session.add_all(entries)
    session.flush()
    try:
        vectors.upsert(
            knowledge_base.id,
            [entry.id for entry in entries],
            [entry.content for entry in entries],
            [{"external_id": entry.external_id, "title": entry.title} for entry in entries],
        )
        session.commit()
    except Exception:
        session.rollback()
        try:
            vectors.delete_knowledge_base(knowledge_base.id)
        finally:
            raise
    session.refresh(knowledge_base)
    return knowledge_base


def add_entry(
    session: Session,
    knowledge_base: KnowledgeBase,
    data: KnowledgeEntryCreate,
    vectors: VectorStoreProtocol,
) -> KnowledgeEntry:
    existing = session.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.knowledge_base_id == knowledge_base.id,
            KnowledgeEntry.external_id == data.id,
        )
    )
    if existing is not None:
        raise KnowledgeEntryConflictError(f"知识条目 id 已存在：{data.id}")

    entry = KnowledgeEntry(
        external_id=data.id,
        knowledge_base_id=knowledge_base.id,
        title=data.title,
        content=data.content,
        extra_metadata=data.metadata,
    )
    session.add(entry)
    session.flush()
    try:
        vectors.upsert(
            knowledge_base.id,
            [entry.id],
            [entry.content],
            [{"external_id": entry.external_id, "title": entry.title}],
        )
        knowledge_base.updated_at = utc_now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(entry)
    return entry


def update_entry(
    session: Session,
    entry: KnowledgeEntry,
    data: KnowledgeEntryUpdate,
    vectors: VectorStoreProtocol,
) -> KnowledgeEntry:
    values = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in values.items():
        setattr(entry, "extra_metadata" if field == "metadata" else field, value)
    try:
        # 先触发数据库约束校验，避免数据库失败时留下已更新的向量。
        session.flush()
        vectors.upsert(
            entry.knowledge_base_id,
            [entry.id],
            [entry.content],
            [{"external_id": entry.external_id, "title": entry.title}],
        )
        entry.updated_at = utc_now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(entry)
    return entry


def delete_entry(
    session: Session,
    entry: KnowledgeEntry,
    vectors: VectorStoreProtocol,
) -> None:
    session.delete(entry)
    try:
        # 先验证数据库删除可执行，再同步删除向量；向量失败时回滚数据库事务。
        session.flush()
        vectors.delete_entry(entry.knowledge_base_id, entry.id)
        session.commit()
    except Exception:
        session.rollback()
        raise


def delete_knowledge_base(
    session: Session,
    knowledge_base: KnowledgeBase,
    vectors: VectorStoreProtocol,
) -> None:
    active_tasks = list(
        session.scalars(
            select(DetectionTask).where(
                DetectionTask.knowledge_base_id == knowledge_base.id,
                DetectionTask.status.in_(NON_TERMINAL_TASK_STATUSES),
            )
        )
    )
    if active_tasks:
        names = "、".join(item.name for item in active_tasks[:3])
        raise KnowledgeBaseInUseError(
            f"该知识库正被 {len(active_tasks)} 个未结束任务使用（{names}），请先取消或完成任务"
        )

    # 已完成任务已经持有证据快照，解除引用后仍可查看历史检测结果。
    historical_tasks = session.scalars(
        select(DetectionTask).where(DetectionTask.knowledge_base_id == knowledge_base.id)
    )
    for task in historical_tasks:
        task.knowledge_base_id = None
    session.delete(knowledge_base)
    try:
        # 先验证 SQLite 约束，避免向量集合删除后数据库事务才失败。
        session.flush()
        vectors.delete_knowledge_base(knowledge_base.id)
        session.commit()
    except Exception:
        session.rollback()
        raise


def entry_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(KnowledgeEntry.knowledge_base_id, func.count(KnowledgeEntry.id)).group_by(
            KnowledgeEntry.knowledge_base_id
        )
    )
    return {knowledge_base_id: count for knowledge_base_id, count in rows}
