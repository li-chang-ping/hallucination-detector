from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, CategoryVersion, Severity, utc_now
from app.schemas.categories import CategoryCreate, CategoryUpdate

DEFAULT_CATEGORIES = (
    CategoryCreate(
        name="政策与优惠错误",
        description="编造或错误描述退换货、发票、优惠等规则",
        default_severity=Severity.HIGH,
        prompt_guidance="核对适用期限、条件、费用承担、活动门槛和办理入口。",
    ),
    CategoryCreate(
        name="产品参数错误",
        description="材质、规格、接口、功能、保修等与证据冲突或无依据",
        default_severity=Severity.HIGH,
        prompt_guidance="任何具体参数都必须由检索证据明确支持。",
    ),
    CategoryCreate(
        name="事实信息编造",
        description="地址、门店、品牌关系、物流状态等虚构信息",
        default_severity=Severity.HIGH,
        prompt_guidance="不得把知识库未提供的事实表述为已确认。",
    ),
    CategoryCreate(
        name="能力越界",
        description="声称完成实际不具备的查询、修改、发券或工单操作",
        default_severity=Severity.HIGH,
        prompt_guidance="重点识别‘已查询、已修改、已发放、已升级’等执行承诺。",
    ),
    CategoryCreate(
        name="安全误导",
        description="可能造成健康、人身或重大财产风险的错误建议",
        default_severity=Severity.CRITICAL,
        prompt_guidance="健康安全信息存在限制时，不得改写为无条件安全。",
    ),
    CategoryCreate(
        name="关键信息遗漏",
        description="遗漏会实质改变结论的重要限制或风险信息",
        default_severity=Severity.MEDIUM,
        prompt_guidance="仅在遗漏足以让用户形成相反或明显错误判断时命中。",
    ),
)


def seed_default_categories(session: Session) -> None:
    if session.scalar(select(Category.id).limit(1)) is not None:
        return
    for item in DEFAULT_CATEGORIES:
        category = Category(**item.model_dump(mode="json"))
        session.add(category)
        session.flush()
        record_category_version(session, category, source="initial", note="初始化默认分类")
    session.commit()


def category_snapshot(category: Category) -> dict[str, object]:
    return {
        "name": category.name,
        "description": category.description,
        "default_severity": category.default_severity,
        "prompt_guidance": category.prompt_guidance,
        "is_active": category.is_active,
        "is_archived": category.is_archived,
    }


def record_category_version(
    session: Session, category: Category, *, source: str, note: str
) -> CategoryVersion:
    version = CategoryVersion(
        category_id=category.id,
        snapshot=category_snapshot(category),
        source=source,
        note=note,
    )
    session.add(version)
    return version


def create_category(session: Session, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump(mode="json"))
    session.add(category)
    session.flush()
    record_category_version(session, category, source="manual", note="创建分类")
    session.commit()
    session.refresh(category)
    return category


def update_category(
    session: Session,
    category: Category,
    data: CategoryUpdate,
    *,
    source: str = "manual",
    note: str = "编辑分类",
) -> Category:
    ensure_category_version(session, category)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True, mode="json").items():
        setattr(category, field, value)
    category.updated_at = utc_now()
    record_category_version(session, category, source=source, note=note)
    session.commit()
    session.refresh(category)
    return category


def ensure_category_version(session: Session, category: Category) -> None:
    """为升级前已有分类补一份当前状态，确保首次打开历史即可回退。"""
    exists = session.scalar(
        select(CategoryVersion.id).where(CategoryVersion.category_id == category.id).limit(1)
    )
    if exists is None:
        record_category_version(session, category, source="initial", note="迁移时记录当前定义")
        session.commit()


def rollback_category(session: Session, category: Category, version: CategoryVersion) -> Category:
    snapshot = version.snapshot
    for field in (
        "name",
        "description",
        "default_severity",
        "prompt_guidance",
        "is_active",
        "is_archived",
    ):
        if field in snapshot:
            setattr(category, field, snapshot[field])
    category.updated_at = utc_now()
    record_category_version(
        session,
        category,
        source="rollback",
        note=f"回退到版本 {version.id}",
    )
    session.commit()
    session.refresh(category)
    return category
