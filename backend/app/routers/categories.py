from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category, CategoryVersion, utc_now
from app.schemas.categories import CategoryCreate, CategoryRead, CategoryUpdate, CategoryVersionRead
from app.services.categories import (
    create_category,
    ensure_category_version,
    record_category_version,
    rollback_category,
    update_category,
)

router = APIRouter(prefix="/categories", tags=["categories"])
DbSession = Annotated[Session, Depends(get_db)]


def get_category_or_404(
    session: Session, category_id: str, *, allow_archived: bool = False
) -> Category:
    category = session.get(Category, category_id)
    if category is None or (category.is_archived and not allow_archived):
        raise HTTPException(status_code=404, detail="幻觉分类不存在")
    return category


@router.get("", response_model=list[CategoryRead])
def list_categories(
    session: DbSession,
    include_inactive: bool = Query(default=True),
    include_archived: bool = Query(default=False),
) -> list[Category]:
    statement = select(Category).order_by(Category.created_at)
    if not include_archived:
        statement = statement.where(Category.is_archived.is_(False))
    if not include_inactive:
        statement = statement.where(Category.is_active.is_(True))
    return list(session.scalars(statement))


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def add_category(data: CategoryCreate, session: DbSession) -> Category:
    try:
        return create_category(session, data)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="分类名称已存在") from exc


@router.put("/{category_id}", response_model=CategoryRead)
def edit_category(category_id: str, data: CategoryUpdate, session: DbSession) -> Category:
    category = get_category_or_404(session, category_id)
    try:
        return update_category(session, category, data)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="分类名称已存在") from exc


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_category(category_id: str, session: DbSession) -> None:
    category = get_category_or_404(session, category_id)
    ensure_category_version(session, category)
    category.is_archived = True
    category.is_active = False
    category.updated_at = utc_now()
    record_category_version(session, category, source="manual", note="归档分类")
    session.commit()


@router.get("/{category_id}/versions", response_model=list[CategoryVersionRead])
def list_category_versions(category_id: str, session: DbSession) -> list[CategoryVersion]:
    category = get_category_or_404(session, category_id, allow_archived=True)
    ensure_category_version(session, category)
    return list(
        session.scalars(
            select(CategoryVersion)
            .where(CategoryVersion.category_id == category_id)
            .order_by(CategoryVersion.created_at.desc())
        )
    )


@router.post("/{category_id}/rollback/{version_id}", response_model=CategoryRead)
def restore_category(category_id: str, version_id: str, session: DbSession) -> Category:
    category = get_category_or_404(session, category_id, allow_archived=True)
    version = session.get(CategoryVersion, version_id)
    if version is None or version.category_id != category_id:
        raise HTTPException(status_code=404, detail="分类历史版本不存在")
    try:
        return rollback_category(session, category, version)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="历史版本中的分类名称已被占用") from exc
