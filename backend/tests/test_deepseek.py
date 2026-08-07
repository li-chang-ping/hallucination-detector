import pytest

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
