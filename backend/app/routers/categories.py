from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category, utc_now
from app.schemas.categories import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.categories import create_category, update_category

router = APIRouter(prefix="/categories", tags=["categories"])
DbSession = Annotated[Session, Depends(get_db)]


def get_category_or_404(session: Session, category_id: str) -> Category:
    category = session.get(Category, category_id)
    if category is None or category.is_archived:
        raise HTTPException(status_code=404, detail="幻觉分类不存在")
    return category


@router.get("", response_model=list[CategoryRead])
def list_categories(
    session: DbSession, include_inactive: bool = Query(default=True)
) -> list[Category]:
    statement = (
        select(Category).where(Category.is_archived.is_(False)).order_by(Category.created_at)
    )
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
    category.is_archived = True
    category.is_active = False
    category.updated_at = utc_now()
    session.commit()
