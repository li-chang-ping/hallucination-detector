from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Category, CategoryVersion, Severity
from app.schemas.categories import CategoryCreate, CategoryUpdate
from app.services.categories import (
    create_category,
    rollback_category,
    seed_default_categories,
    update_category,
)


def test_seed_and_update_categories() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_default_categories(session)
        categories = list(session.scalars(select(Category)))
        assert len(categories) == 6
        assert {item.default_severity for item in categories} >= {"high", "critical", "medium"}

        custom = create_category(
            session,
            CategoryCreate(
                name="测试分类",
                description="用于验证更新",
                default_severity=Severity.LOW,
            ),
        )
        updated = update_category(session, custom, CategoryUpdate(is_active=False))
        assert updated.is_active is False
        versions = list(
            session.scalars(select(CategoryVersion).where(CategoryVersion.category_id == custom.id))
        )
        assert len(versions) == 2
        assert versions[0].snapshot["is_active"] is True

        restored = rollback_category(session, custom, versions[0])
        assert restored.is_active is True
        assert (
            len(
                list(
                    session.scalars(
                        select(CategoryVersion).where(CategoryVersion.category_id == custom.id)
                    )
                )
            )
            == 3
        )
