import copy
import json

import pytest

from app.config import Settings
from app.schemas.evaluations import (
    CategorySuggestionDraft,
    EvaluationAnalysisResponse,
)
from app.services import deepseek as deepseek_module
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

    with pytest.raises(ValueError, match="必须归档或重命名"):
        DeepSeekClient._validate_suggestions(
            create_only,
            {"政策与优惠错误"},
            {"政策编造"},
            mismatch_sources={"政策与优惠错误"},
            human_names={"政策编造"},
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
        mismatch_sources={"政策与优惠错误"},
        human_names={"政策编造"},
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
async def test_analysis_retry_feeds_validation_error_back_to_model(monkeypatch) -> None:
    invalid_result = {
        "analyses": [
            {
                "input_id": "h04",
                "error_type": "false_positive",
                "reason": "分类名称不一致",
                "likely_cause": "模型选择了重叠分类",
                "evidence_summary": "",
            },
            {
                "input_id": "h20",
                "error_type": "false_positive",
                "reason": "分类名称不一致",
                "likely_cause": "模型选择了重叠分类",
                "evidence_summary": "",
            },
        ],
        "suggestions": [
            {
                "action": "update",
                "target_category_name": "政策偏差",
                "reason": "错误地反向对齐名称",
                "proposed_name": "政策编造",
            },
            {
                "action": "update",
                "target_category_name": "信息遗漏",
                "reason": "错误地反向对齐名称",
                "proposed_name": "信息编造",
            },
        ],
    }
    corrected_result = {
        "analyses": invalid_result["analyses"],
        "suggestions": [
            {
                "action": "archive",
                "target_category_name": "政策编造",
                "reason": "人工标准分类政策偏差已经存在，应清理导致误报的重叠分类",
            },
            {
                "action": "archive",
                "target_category_name": "信息编造",
                "reason": "人工标准分类信息遗漏已经存在，应清理导致误报的重叠分类",
            },
        ],
    }

    class FakeResponse:
        def __init__(self, content: dict[str, object]) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": json.dumps(self.content)}}]}

    class FakeAsyncClient:
        responses = [invalid_result, corrected_result]
        requests: list[dict[str, object]] = []

        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append(copy.deepcopy(kwargs["json"]))
            return FakeResponse(self.responses.pop(0))

    async def no_sleep(_: int) -> None:
        return None

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(deepseek_module.asyncio, "sleep", no_sleep)
    client = DeepSeekClient(Settings(deepseek_api_key="test-key"))
    error_cases = [
        {
            "input_id": "h04",
            "error_type": "false_positive",
            "human_category": "政策偏差",
            "predicted_category": "政策编造",
        },
        {
            "input_id": "h20",
            "error_type": "false_positive",
            "human_category": "信息遗漏",
            "predicted_category": "信息编造",
        },
    ]
    categories = [{"name": name} for name in ("政策偏差", "政策编造", "信息遗漏", "信息编造")]

    result = await client.analyze_evaluation(error_cases, categories)

    assert [(item.action, item.target_category_name) for item in result.suggestions] == [
        ("archive", "政策编造"),
        ("archive", "信息编造"),
    ]
    assert len(FakeAsyncClient.requests) == 2
    retry_messages = FakeAsyncClient.requests[1]["messages"]
    assert isinstance(retry_messages, list)
    correction = retry_messages[-1]["content"]
    assert "重命名目标已存在" in correction
    assert '"existing_human_category_names": ["信息遗漏", "政策偏差"]' in correction
    assert '"obsolete_prediction_category_names": ["信息编造", "政策编造"]' in correction
