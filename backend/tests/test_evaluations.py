from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Category,
    CategorySuggestion,
    CategoryVersion,
    DetectionItem,
    Evaluation,
    Severity,
)
from app.schemas.evaluations import EvaluationRead, GroundTruthBatch, GroundTruthItem
from app.services.deepseek import DeepSeekClient, DeepSeekError
from app.services.evaluations import (
    _fallback_analysis,
    build_error_cases,
    calculate_metrics,
    create_evaluation_insights,
    decide_suggestion,
    decide_suggestion_plan,
    record_evaluation_progress,
    validate_ground_truth_ids,
)


def prediction(
    item_id: str,
    is_hallucination: bool,
    primary: str | None = None,
    categories: list[str] | None = None,
) -> DetectionItem:
    return DetectionItem(
        task_id="task",
        input_id=item_id,
        position=0,
        user_question="问题",
        system_reply="回复",
        status="completed",
        is_hallucination=is_hallucination,
        primary_category=primary,
        category_names=categories if categories is not None else ([primary] if primary else []),
    )


def test_ground_truth_batch_rejects_empty_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        GroundTruthBatch(items=[])

    duplicate = GroundTruthItem(id="h01", is_hallucination=False)
    with pytest.raises(ValidationError, match="id 必须唯一"):
        GroundTruthBatch(items=[duplicate, duplicate])


def test_ground_truth_ids_must_match_task_items() -> None:
    predictions = [prediction("h01", False), prediction("h02", False)]
    truths = [GroundTruthItem(id="h01", is_hallucination=False)]

    with pytest.raises(ValueError, match="缺少任务 ID：h02"):
        validate_ground_truth_ids(predictions, truths)


def test_missing_model_result_is_not_silently_excluded() -> None:
    unresolved = prediction("h01", False)
    unresolved.is_hallucination = None
    truths = [GroundTruthItem(id="h01", is_hallucination=True, hallucination_type="政策错误")]

    metrics = calculate_metrics([unresolved], truths)

    assert metrics["evaluated_count"] == 1
    assert metrics["prediction_count"] == 0
    assert metrics["fn"] == 1
    assert metrics["recall"] == 0
    assert metrics["false_negative_ids"] == ["h01"]


def test_calculate_binary_and_category_metrics() -> None:
    predictions = [
        prediction("h01", True, "政策编造"),
        prediction("h02", False),
        prediction("h03", True, "事实信息编造"),
    ]
    truths = [
        GroundTruthItem(id="h01", is_hallucination=True, hallucination_type="政策编造"),
        GroundTruthItem(id="h02", is_hallucination=True, hallucination_type="参数编造"),
        GroundTruthItem(id="h03", is_hallucination=False),
    ]
    metrics = calculate_metrics(predictions, truths)
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["false_negative_ids"] == ["h02"]
    assert "f1" not in metrics
    assert "category_accuracy" not in metrics
    assert "category_stats" not in metrics


def test_category_mismatch_is_counted_as_business_false_positive() -> None:
    predictions = [prediction("h08", True, "事实信息编造")]
    truths = [GroundTruthItem(id="h08", is_hallucination=True, hallucination_type="政策偏差")]

    metrics = calculate_metrics(predictions, truths)

    assert metrics["tp"] == 0
    assert metrics["fp"] == 1
    assert metrics["fn"] == 0
    assert metrics["false_positive_ids"] == ["h08"]
    assert metrics["category_mismatch_ids"] == ["h08"]
    assert metrics["category_mismatches"] == [
        {
            "id": "h08",
            "expected_category": "政策偏差",
            "predicted_category": "事实信息编造",
        }
    ]
    assert metrics["binary_confusion_matrix"] == {"tp": 1, "tn": 0, "fp": 0, "fn": 0}


def test_primary_category_mismatch_is_business_false_positive() -> None:
    predictions = [
        prediction(
            "h03",
            True,
            "事实信息编造",
            categories=["事实信息编造", "能力越界"],
        )
    ]
    truths = [GroundTruthItem(id="h03", is_hallucination=True, hallucination_type="能力越界")]

    metrics = calculate_metrics(predictions, truths)

    assert metrics["tp"] == 0
    assert metrics["fp"] == 1
    assert metrics["category_mismatch_ids"] == ["h03"]


def test_evaluation_response_removes_unsupported_historical_metrics() -> None:
    result = EvaluationRead.model_validate(
        {
            "id": "evaluation",
            "task_id": "task",
            "metrics": {
                "recall": 1.0,
                "f1": 0.9,
                "category_accuracy": 0.8,
                "category_stats": {},
            },
            "ground_truth_count": 20,
            "created_at": datetime.now(UTC),
        }
    )

    assert result.metrics == {"recall": 1.0}


def test_evaluation_progress_is_persisted_as_replayable_events() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        evaluation = Evaluation(task_id="task", metrics={}, ground_truth_count=1)
        session.add(evaluation)
        session.commit()

        record_evaluation_progress(
            session,
            evaluation,
            "发现 2 条误判，正在准备分析上下文",
            35,
            status="running",
        )
        record_evaluation_progress(session, evaluation, "优化方案校验通过", 92)

        session.refresh(evaluation)
        assert evaluation.insight_status == "running"
        assert evaluation.insight_progress == 92
        assert evaluation.insight_stage == "优化方案校验通过"
        assert [event["sequence"] for event in evaluation.insight_events] == [1, 2]
        assert evaluation.insight_events[0]["progress"] == 35


def test_build_error_cases_keeps_context_for_analysis() -> None:
    item = prediction("h08", True, "事实信息编造")
    item.rationale = "回复给出了错误地址"
    truths = [
        GroundTruthItem(
            id="h08",
            is_hallucination=True,
            hallucination_type="政策偏差",
            detail="应归入政策错误",
        )
    ]
    metrics = calculate_metrics([item], truths)

    cases = build_error_cases([item], truths, metrics)

    assert cases[0]["error_type"] == "false_positive"
    assert cases[0]["human_category"] == "政策偏差"
    assert cases[0]["predicted_category"] == "事实信息编造"
    reason, cause = _fallback_analysis(cases[0])
    assert "人工分类为“政策偏差”" in reason
    assert "不做任何映射" in cause


@pytest.mark.asyncio
async def test_insight_failure_is_visible_without_deterministic_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    item = prediction("h01", True, "政策与优惠错误")
    truths = [GroundTruthItem(id="h01", is_hallucination=True, hallucination_type="政策编造")]

    async def fail_analysis(*_args: object, **_kwargs: object) -> object:
        raise DeepSeekError("模型未返回有效建议")

    monkeypatch.setattr(DeepSeekClient, "analyze_evaluation", fail_analysis)
    with Session(engine) as session:
        session.add_all(
            [
                Category(
                    name="政策与优惠错误",
                    description="宽泛政策分类",
                    default_severity=Severity.HIGH,
                ),
                Category(
                    name="政策编造",
                    description="人工细分类",
                    default_severity=Severity.HIGH,
                ),
            ]
        )
        evaluation = Evaluation(
            task_id="task",
            metrics=calculate_metrics([item], truths),
            ground_truth_count=1,
        )
        session.add(evaluation)
        session.flush()

        await create_evaluation_insights(session, evaluation, [item], truths)

        assert evaluation.insight_status == "fallback"
        assert evaluation.insight_error == "模型未返回有效建议"
        assert evaluation.suggestions == []
        assert len(evaluation.analyses) == 1


def test_apply_suggestion_updates_category_and_creates_version() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        category = Category(
            name="政策与优惠错误",
            description="旧定义",
            default_severity=Severity.HIGH,
            prompt_guidance="旧指引",
        )
        evaluation = Evaluation(task_id="task", metrics={}, ground_truth_count=1)
        session.add_all([category, evaluation])
        session.flush()
        suggestion = CategorySuggestion(
            evaluation_id=evaluation.id,
            category_id=category.id,
            target_category_name=category.name,
            reason="分类边界需要明确",
            proposed_changes={"prompt_guidance": "新指引"},
        )
        session.add(suggestion)
        session.commit()

        decided = decide_suggestion(session, suggestion, apply=True)

        assert decided.status == "applied"
        assert category.prompt_guidance == "新指引"
        versions = list(
            session.scalars(
                select(CategoryVersion).where(CategoryVersion.category_id == category.id)
            )
        )
        assert len(versions) == 2
        assert versions[0].snapshot["prompt_guidance"] == "旧指引"
        assert versions[1].snapshot["prompt_guidance"] == "新指引"


def test_apply_create_and_archive_suggestions() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        evaluation = Evaluation(task_id="task", metrics={}, ground_truth_count=1)
        session.add(evaluation)
        session.flush()
        create_suggestion = CategorySuggestion(
            evaluation_id=evaluation.id,
            category_id=None,
            action="create",
            target_category_name="政策偏差",
            reason="人工分类缺少对应定义",
            proposed_changes={
                "description": "政策内容与证据存在部分偏差",
                "default_severity": "high",
                "prompt_guidance": "识别部分正确、部分错误的政策回复",
            },
        )
        session.add(create_suggestion)
        session.commit()

        decided_create = decide_suggestion(session, create_suggestion, apply=True)
        created = session.scalar(select(Category).where(Category.name == "政策偏差"))
        assert decided_create.status == "applied"
        assert created is not None
        assert decided_create.category_id == created.id

        archive_suggestion = CategorySuggestion(
            evaluation_id=evaluation.id,
            category_id=created.id,
            action="archive",
            target_category_name=created.name,
            reason="分类已不再使用",
            proposed_changes={},
        )
        session.add(archive_suggestion)
        session.commit()

        decide_suggestion(session, archive_suggestion, apply=True)
        assert created.is_archived is True
        assert created.is_active is False


def test_apply_suggestion_plan_is_atomic() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broad = Category(
            name="政策与优惠错误",
            description="宽泛分类",
            default_severity=Severity.HIGH,
        )
        evaluation = Evaluation(task_id="task", metrics={}, ground_truth_count=1)
        session.add_all([broad, evaluation])
        session.flush()
        archive = CategorySuggestion(
            evaluation_id=evaluation.id,
            category_id=broad.id,
            action="archive",
            target_category_name=broad.name,
            reason="由细分类替代",
            proposed_changes={},
        )
        conflicting_create = CategorySuggestion(
            evaluation_id=evaluation.id,
            action="create",
            target_category_name=broad.name,
            reason="故意制造名称冲突",
            proposed_changes={"description": "重复名称", "default_severity": "high"},
        )
        session.add_all([archive, conflicting_create])
        session.commit()

        with pytest.raises(IntegrityError):
            decide_suggestion_plan(session, evaluation, apply=True)

        assert session.get(Category, broad.id).is_archived is False
        assert session.get(CategorySuggestion, archive.id).status == "pending"
        assert session.get(CategorySuggestion, conflicting_create.id).status == "pending"


def test_apply_complete_suggestion_plan() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broad = Category(
            name="政策与优惠错误",
            description="宽泛分类",
            default_severity=Severity.HIGH,
        )
        evaluation = Evaluation(task_id="task", metrics={}, ground_truth_count=1)
        session.add_all([broad, evaluation])
        session.flush()
        session.add_all(
            [
                CategorySuggestion(
                    evaluation_id=evaluation.id,
                    action="create",
                    target_category_name="政策编造",
                    reason="新增人工细分类",
                    proposed_changes={
                        "description": "编造政策规则",
                        "default_severity": "high",
                    },
                ),
                CategorySuggestion(
                    evaluation_id=evaluation.id,
                    category_id=broad.id,
                    action="archive",
                    target_category_name=broad.name,
                    reason="细分类已覆盖",
                    proposed_changes={},
                ),
            ]
        )
        session.commit()

        suggestions = decide_suggestion_plan(session, evaluation, apply=True)

        assert {item.status for item in suggestions} == {"applied"}
        assert session.get(Category, broad.id).is_archived is True
        assert session.scalar(select(Category).where(Category.name == "政策编造")) is not None
