import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import KnowledgeBase, KnowledgeEntry
from app.schemas.knowledge import (
    KnowledgeBaseRead,
    KnowledgeEntryCreate,
    KnowledgeEntryRead,
    KnowledgeEntryUpdate,
    KnowledgeImport,
)
from app.services.knowledge import add_entry, entry_counts, import_knowledge_base, update_entry
from app.services.vector_store import VectorStore, VectorStoreError, get_vector_store

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])
DbSession = Annotated[Session, Depends(get_db)]
Vectors = Annotated[VectorStore, Depends(get_vector_store)]


def kb_or_404(session: Session, knowledge_base_id: str) -> KnowledgeBase:
    item = session.get(KnowledgeBase, knowledge_base_id)
    if item is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return item


def entry_or_404(session: Session, knowledge_base_id: str, entry_id: str) -> KnowledgeEntry:
    entry = session.get(KnowledgeEntry, entry_id)
    if entry is None or entry.knowledge_base_id != knowledge_base_id:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return entry


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(session: DbSession) -> list[KnowledgeBaseRead]:
    counts = entry_counts(session)
    items = session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    return [
        KnowledgeBaseRead.model_validate(item).model_copy(
            update={"entry_count": counts.get(item.id, 0)}
        )
        for item in items
    ]


@router.post("/import", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
async def upload_knowledge_base(
    session: DbSession, vectors: Vectors, file: Annotated[UploadFile, File()]
) -> KnowledgeBaseRead:
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 JSON 文件")
    try:
        data = KnowledgeImport.model_validate(json.loads((await file.read()).decode("utf-8")))
        item = import_knowledge_base(session, data, vectors)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"知识库 JSON 格式错误: {exc}") from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="知识库名称已存在") from exc
    except VectorStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return KnowledgeBaseRead.model_validate(item).model_copy(
        update={"entry_count": len(data.entries)}
    )


@router.get("/{knowledge_base_id}/entries", response_model=list[KnowledgeEntryRead])
def list_entries(knowledge_base_id: str, session: DbSession) -> list[KnowledgeEntry]:
    kb_or_404(session, knowledge_base_id)
    return list(
        session.scalars(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.knowledge_base_id == knowledge_base_id)
            .order_by(KnowledgeEntry.created_at)
        )
    )


@router.post(
    "/{knowledge_base_id}/entries",
    response_model=KnowledgeEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_entry(
    knowledge_base_id: str, data: KnowledgeEntryCreate, session: DbSession, vectors: Vectors
) -> KnowledgeEntry:
    return add_entry(session, kb_or_404(session, knowledge_base_id), data, vectors)


@router.put("/{knowledge_base_id}/entries/{entry_id}", response_model=KnowledgeEntryRead)
def edit_entry(
    knowledge_base_id: str,
    entry_id: str,
    data: KnowledgeEntryUpdate,
    session: DbSession,
    vectors: Vectors,
) -> KnowledgeEntry:
    return update_entry(session, entry_or_404(session, knowledge_base_id, entry_id), data, vectors)


@router.delete("/{knowledge_base_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_entry(
    knowledge_base_id: str, entry_id: str, session: DbSession, vectors: Vectors
) -> None:
    entry = entry_or_404(session, knowledge_base_id, entry_id)
    vectors.delete_entry(knowledge_base_id, entry.id)
    session.delete(entry)
    session.commit()


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_knowledge_base(knowledge_base_id: str, session: DbSession, vectors: Vectors) -> None:
    item = kb_or_404(session, knowledge_base_id)
    vectors.delete_knowledge_base(knowledge_base_id)
    session.delete(item)
    session.commit()
