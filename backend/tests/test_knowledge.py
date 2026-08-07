from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import KnowledgeEntry
from app.schemas.knowledge import KnowledgeEntryCreate, KnowledgeImport
from app.services.knowledge import add_entry, import_knowledge_base


class FakeVectors:
    def __init__(self) -> None:
        self.documents: dict[str, str] = {}

    def upsert(
        self,
        _knowledge_base_id: str,
        ids: list[str],
        documents: list[str],
        _metadatas: list[dict[str, Any]],
    ) -> None:
        self.documents.update(zip(ids, documents, strict=True))

    def delete_entry(self, _knowledge_base_id: str, entry_id: str) -> None:
        self.documents.pop(entry_id, None)

    def delete_knowledge_base(self, _knowledge_base_id: str) -> None:
        self.documents.clear()


def test_import_and_add_entry_sync_vectors() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    vectors = FakeVectors()
    with Session(engine) as session:
        knowledge_base = import_knowledge_base(
            session,
            KnowledgeImport(
                name="测试知识库",
                entries=[KnowledgeEntryCreate(id="kb-1", content="支持七天无理由退货")],
            ),
            vectors,
        )
        assert len(vectors.documents) == 1
        entry = add_entry(
            session,
            knowledge_base,
            KnowledgeEntryCreate(id="kb-2", content="不支持货到付款"),
            vectors,
        )
        assert vectors.documents[entry.id] == "不支持货到付款"
        assert len(list(session.scalars(select(KnowledgeEntry)))) == 2
