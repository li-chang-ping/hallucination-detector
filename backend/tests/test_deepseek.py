import pytest

from app.config import get_settings
from app.schemas.evaluations import (
    CategorySuggestionDraft,
    EvaluationAnalysisResponse,
)
from app.services.deepseek import DeepSeekClient


def suggestion(action: str, target: str, **changes: object) -> CategorySuggestionDraft:
    return CategorySuggestionDraft.model_validate(
        {
            "action": action,
            "target_category_name": target,
            "reason": "分类名称需要与人工标注对齐",
            **changes,
        }
    )


def test_suggestion_validation_requires_name_alignment() -> None:
    result = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "update",
                "政策与优惠错误",
                proposed_description="更清晰的政策错误定义",
            )
        ],
    )

    with pytest.raises(ValueError, match="缺少分类名称对齐建议"):
        DeepSeekClient._validate_suggestions(
            result,
            {"政策与优惠错误"},
            {"政策偏差"},
        )


def test_suggestion_validation_rejects_empty_result_when_errors_exist() -> None:
    with pytest.raises(ValueError, match="存在误判但未返回优化建议"):
        DeepSeekClient._validate_suggestions(
            EvaluationAnalysisResponse(analyses=[], suggestions=[]),
            {"政策与优惠错误", "政策编造"},
            set(),
        )


def test_suggestion_validation_accepts_create_or_rename() -> None:
    result = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "create",
                "政策偏差",
                proposed_description="政策内容部分正确但存在实质偏差",
                proposed_default_severity="high",
            )
        ],
    )

    DeepSeekClient._validate_suggestions(
        result,
        {"政策与优惠错误"},
        {"政策偏差"},
    )


def test_suggestion_validation_rejects_create_and_rename_conflict() -> None:
    result = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "create",
                "信息编造",
                proposed_description="编造事实信息",
                proposed_default_severity="high",
            ),
            suggestion(
                "update",
                "事实信息编造",
                proposed_name="信息编造",
            ),
        ],
    )

    with pytest.raises(ValueError, match="新增与重命名建议冲突"):
        DeepSeekClient._validate_suggestions(
            result,
            {"事实信息编造"},
            {"信息编造"},
        )


def test_suggestion_validation_requires_obsolete_source_cleanup() -> None:
    create_only = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "create",
                "政策编造",
                proposed_description="编造政策规则",
                proposed_default_severity="high",
            )
        ],
    )

    with pytest.raises(ValueError, match="必须归档、重命名或更新"):
        DeepSeekClient._validate_suggestions(
            create_only,
            {"政策与优惠错误"},
            {"政策编造"},
            migration_sources={"政策与优惠错误"},
        )

    coherent_plan = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "create",
                "政策编造",
                proposed_description="编造政策规则",
                proposed_default_severity="high",
            ),
            suggestion("archive", "政策与优惠错误"),
        ],
    )
    DeepSeekClient._validate_suggestions(
        coherent_plan,
        {"政策与优惠错误"},
        {"政策编造"},
        migration_sources={"政策与优惠错误"},
    )


def test_suggestion_validation_protects_categories_with_correct_hits() -> None:
    result = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[suggestion("archive", "信息编造")],
    )

    with pytest.raises(ValueError, match="仍有正确命中的分类不能归档或改名"):
        DeepSeekClient._validate_suggestions(
            result,
            {"信息编造", "信息遗漏"},
            set(),
            protected_names={"信息编造", "信息遗漏"},
        )


def test_suggestion_validation_rejects_rename_to_existing_category() -> None:
    result = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[suggestion("update", "政策编造", proposed_name="政策与优惠错误")],
    )

    with pytest.raises(ValueError, match="重命名目标已存在"):
        DeepSeekClient._validate_suggestions(
            result,
            {"政策编造", "政策与优惠错误"},
            set(),
        )


@pytest.mark.asyncio
async def test_real_analysis_uses_performance_to_generate_boundary_updates() -> None:
    settings = get_settings()
    if not settings.deepseek_api_key:
        pytest.skip("未配置 DEEPSEEK_API_KEY，跳过真实 API 集成测试")
    client = DeepSeekClient(settings)
    error_cases = [
        {
            "input_id": "h19",
            "error_type": "false_positive",
            "human_category": "优惠编造",
            "predicted_category": "政策编造",
        },
        {
            "input_id": "h20",
            "error_type": "false_positive",
            "human_category": "信息遗漏",
            "predicted_category": "信息编造",
        },
    ]
    categories = [
        {
            "name": "优惠编造",
            "description": "编造不存在的优惠活动、优惠券或折扣。",
            "default_severity": "high",
            "prompt_guidance": "核对优惠门槛和条件。",
        },
        {
            "name": "政策编造",
            "description": "编造不存在的政策或规则。",
            "default_severity": "high",
            "prompt_guidance": "核对政策具体条款。",
        },
        {
            "name": "信息遗漏",
            "description": "遗漏会实质改变结论的重要信息。",
            "default_severity": "medium",
            "prompt_guidance": "遗漏限制条件导致错误结论时命中。",
        },
        {
            "name": "信息编造",
            "description": "编造地址、门店或品牌关系等事实信息。",
            "default_severity": "high",
            "prompt_guidance": "无证据支持的事实陈述属于信息编造。",
        },
    ]
    category_performance = [
        {"category_name": "政策编造", "predicted_count": 2, "correct_count": 1},
        {"category_name": "信息编造", "predicted_count": 5, "correct_count": 3},
    ]
    progress_events: list[tuple[str, int]] = []

    result = await client.analyze_evaluation(
        error_cases,
        categories,
        category_performance=category_performance,
        progress_callback=lambda stage, progress: progress_events.append((stage, progress)),
    )

    assert result.suggestions
    assert all(item.action == "update" for item in result.suggestions)
    assert all(item.proposed_name is None for item in result.suggestions)
    assert {item.target_category_name for item in result.suggestions} <= {
        "优惠编造",
        "政策编造",
        "信息遗漏",
        "信息编造",
    }
    assert any(
        item.proposed_description or item.proposed_prompt_guidance for item in result.suggestions
    )
    assert progress_events[-1] == ("优化方案校验通过，正在保存结果", 92)
