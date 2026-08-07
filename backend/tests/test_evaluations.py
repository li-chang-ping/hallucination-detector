from app.models import DetectionItem
from app.schemas.evaluations import GroundTruthItem
from app.services.evaluations import calculate_metrics


def prediction(
    item_id: str, is_hallucination: bool, primary: str | None = None
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
        category_names=[primary] if primary else [],
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
