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
            "resolved_case_ids": ["h01"],
            "historical_evidence": {"round_count": 2},
            "regression_risk": "medium",
            "regression_risk_reason": "修改分类可能影响相邻边界",
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


def test_suggestion_validation_requires_archiving_recurring_obsolete_category() -> None:
    update_only = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "update",
                "事实信息编造",
                proposed_prompt_guidance="不再选择该分类",
            )
        ],
    )

    with pytest.raises(ValueError, match="必须归档或重命名"):
        DeepSeekClient._validate_suggestions(
            update_only,
            {"事实信息编造", "信息编造"},
            set(),
            obsolete_sources={"事实信息编造"},
        )

    archive = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[suggestion("archive", "事实信息编造")],
    )
    DeepSeekClient._validate_suggestions(
        archive,
        {"事实信息编造", "信息编造"},
        set(),
        obsolete_sources={"事实信息编造"},
    )


def test_suggestion_validation_ignores_already_archived_obsolete_category() -> None:
    current_boundary_update = EvaluationAnalysisResponse(
        analyses=[],
        suggestions=[
            suggestion(
                "update",
                "信息遗漏",
                proposed_prompt_guidance="明确与信息编造的边界",
            )
        ],
    )

    DeepSeekClient._validate_suggestions(
        current_boundary_update,
        {"信息遗漏", "信息编造"},
        set(),
        obsolete_sources={"事实信息编造", "产品参数错误"},
    )


def test_detection_prompt_has_no_concrete_category_anchor() -> None:
    prompt = DeepSeekClient._build_prompt(
        "问题",
        "回复",
        [],
        [{"name": "信息编造", "description": "编造事实", "prompt_guidance": ""}],
    )

    assert "产品参数错误" not in prompt
    assert "优先最具体分类" in prompt
    assert "禁止用宽泛父类" in DeepSeekClient._system_prompt()


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
        optimization_context={
            "history_round_count": 2,
            "target_taxonomy_names": ["优惠编造", "政策编造", "信息遗漏", "信息编造"],
            "recurring_mismatches": [],
            "regression_cases": [],
            "category_lifetime_performance": category_performance,
            "applied_suggestion_history": [],
        },
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


@pytest.mark.asyncio
async def test_real_analysis_archives_recurring_obsolete_category() -> None:
    settings = get_settings()
    if not settings.deepseek_api_key:
        pytest.skip("未配置 DEEPSEEK_API_KEY，跳过真实 API 集成测试")
    client = DeepSeekClient(settings)
    result = await client.analyze_evaluation(
        [
            {
                "input_id": "h07",
                "error_type": "false_positive",
                "human_category": "信息编造",
                "predicted_category": "事实信息编造",
            }
        ],
        [
            {
                "name": "信息编造",
                "description": "编造地址、门店、品牌关系等事实信息。",
                "default_severity": "high",
                "prompt_guidance": "事实信息没有证据或与证据冲突时命中。",
            },
            {
                "name": "事实信息编造",
                "description": "编造地址、门店、品牌关系等事实信息。",
                "default_severity": "high",
                "prompt_guidance": "事实信息没有证据或与证据冲突时命中。",
            },
        ],
        category_performance=[
            {"category_name": "事实信息编造", "predicted_count": 1, "correct_count": 0}
        ],
        optimization_context={
            "history_round_count": 3,
            "target_taxonomy_names": ["信息编造"],
            "recurring_mismatches": [
                {
                    "expected_category": "信息编造",
                    "predicted_category": "事实信息编造",
                    "round_count": 3,
                    "case_ids": ["h07"],
                }
            ],
            "regression_cases": [],
            "category_lifetime_performance": [
                {
                    "category_name": "事实信息编造",
                    "predicted_count": 3,
                    "correct_count": 0,
                    "mismatch_count": 3,
                }
            ],
            "category_conflicts": [
                {
                    "left_category": "信息编造",
                    "right_category": "事实信息编造",
                    "conflict_type": "定义与判断指引完全相同",
                }
            ],
            "applied_suggestion_history": [],
        },
    )

    obsolete = next(
        item for item in result.suggestions if item.target_category_name == "事实信息编造"
    )
    assert obsolete.action == "archive"
    assert "h07" in obsolete.resolved_case_ids
    assert obsolete.regression_risk_reason
