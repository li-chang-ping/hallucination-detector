import pytest
from pydantic import ValidationError

from app.models import Severity
from app.schemas.tasks import DetectionDecision, ReplyBatch, ReplyInput


def test_reply_batch_rejects_duplicate_ids() -> None:
    item = ReplyInput(id="h01", user_question="问题", system_reply="回复")
    with pytest.raises(ValidationError):
        ReplyBatch(items=[item, item])


def test_detection_decision_requires_primary_category() -> None:
    with pytest.raises(ValidationError):
        DetectionDecision(
            is_hallucination=True,
            category_names=["产品参数错误"],
            primary_category="事实信息编造",
            severity=Severity.HIGH,
            confidence=0.9,
            rationale="参数冲突",
        )


def test_detection_decision_rejects_multiple_categories() -> None:
    with pytest.raises(ValidationError):
        DetectionDecision(
            is_hallucination=True,
            category_names=["事实信息编造", "能力越界"],
            primary_category="事实信息编造",
            severity=Severity.HIGH,
            confidence=0.9,
            rationale="同时包含事实编造和能力越界",
        )


def test_normal_decision_clears_categories() -> None:
    result = DetectionDecision(
        is_hallucination=False,
        category_names=["产品参数错误"],
        primary_category="产品参数错误",
        severity=Severity.HIGH,
        confidence=0.98,
        rationale="证据一致",
    )
    assert result.category_names == []
    assert result.severity is None
