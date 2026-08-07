from app.models import DetectionItem
from app.schemas.evaluations import GroundTruthItem
from app.services.evaluations import calculate_metrics


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
    assert metrics["primary_category_accuracy"] == 0.5


def test_category_mismatch_is_counted_as_business_false_positive() -> None:
    predictions = [prediction("h08", True, "事实信息编造")]
    truths = [
        GroundTruthItem(id="h08", is_hallucination=True, hallucination_type="政策偏差")
    ]

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
            "predicted_primary_category": "事实信息编造",
            "predicted_categories": ["事实信息编造"],
        }
    ]
    assert metrics["binary_confusion_matrix"] == {"tp": 1, "tn": 0, "fp": 0, "fn": 0}


def test_expected_multilabel_category_prevents_business_false_positive() -> None:
    predictions = [
        prediction(
            "h03",
            True,
            "事实信息编造",
            categories=["事实信息编造", "能力越界"],
        )
    ]
    truths = [
        GroundTruthItem(id="h03", is_hallucination=True, hallucination_type="能力越界")
    ]

    metrics = calculate_metrics(predictions, truths)

    assert metrics["tp"] == 1
    assert metrics["fp"] == 0
    assert metrics["category_mismatch_ids"] == []
    assert metrics["primary_category_mismatch_ids"] == ["h03"]
