from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Severity, utc_now
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
    session.add_all([Category(**item.model_dump(mode="json")) for item in DEFAULT_CATEGORIES])
    session.commit()


def create_category(session: Session, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump(mode="json"))
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def update_category(session: Session, category: Category, data: CategoryUpdate) -> Category:
    for field, value in data.model_dump(exclude_unset=True, mode="json").items():
        setattr(category, field, value)
    category.updated_at = utc_now()
    session.commit()
    session.refresh(category)
    return category

