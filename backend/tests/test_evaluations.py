from datetime import UTC, datetime

from sqlalchemy import create_engine, select
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
from app.schemas.evaluations import EvaluationRead, GroundTruthItem
from app.services.evaluations import build_error_cases, calculate_metrics, decide_suggestion


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


def test_calculate_binary_and_category_metrics() -> None:
    predictions = [
        prediction("h01", True, "政策与优惠错误"),
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
            "expected_category": "政策与优惠错误",
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
    assert cases[0]["human_category"] == "政策与优惠错误"
    assert cases[0]["predicted_category"] == "事实信息编造"


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
