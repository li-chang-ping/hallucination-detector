import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import DetectionItem, DetectionTask, Severity, TaskStatus
from app.schemas.tasks import DetectionDecision, ReplyBatch, ReplyInput
from app.services.task_runner import fail_task


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


def test_preparation_failure_marks_task_and_pending_items_failed() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        task = DetectionTask(
            name="证据准备失败任务",
            knowledge_base_id=None,
            status=TaskStatus.PREPARING,
            model_name="deepseek-v4-flash",
            total_count=1,
        )
        session.add(task)
        session.flush()
        item = DetectionItem(
            task_id=task.id,
            input_id="h01",
            position=0,
            user_question="问题",
            system_reply="回复",
        )
        session.add(item)
        session.commit()

        fail_task(session, task, "Chroma 查询失败")

        assert task.status == TaskStatus.FAILED
        assert task.error_count == 1
        assert item.status == "failed"
        assert item.error_message == "Chroma 查询失败"
