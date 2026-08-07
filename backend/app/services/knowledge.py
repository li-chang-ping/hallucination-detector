from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import KnowledgeBase, KnowledgeEntry, utc_now
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
    values = data.model_dump(exclude_unset=True)
    for field, value in values.items():
        setattr(entry, "extra_metadata" if field == "metadata" else field, value)
    vectors.upsert(
        entry.knowledge_base_id,
        [entry.id],
        [entry.content],
        [{"external_id": entry.external_id, "title": entry.title}],
    )
    entry.updated_at = utc_now()
    session.commit()
    session.refresh(entry)
    return entry


def entry_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(KnowledgeEntry.knowledge_base_id, func.count(KnowledgeEntry.id)).group_by(
            KnowledgeEntry.knowledge_base_id
        )
    )
    return {knowledge_base_id: count for knowledge_base_id, count in rows}
