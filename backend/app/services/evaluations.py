from collections import Counter

from app.models import DetectionItem
from app.schemas.evaluations import GroundTruthItem

TYPE_MAPPING = {
    "政策编造": "政策与优惠错误",
    "政策偏差": "政策与优惠错误",
    "优惠编造": "政策与优惠错误",
    "参数编造": "产品参数错误",
    "信息编造": "事实信息编造",
    "能力越界": "能力越界",
    "安全误导": "安全误导",
    "信息遗漏": "关键信息遗漏",
}


def _divide(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def calculate_metrics(
    predictions: list[DetectionItem], truths: list[GroundTruthItem]
) -> dict[str, object]:
    prediction_map = {
        item.input_id: item for item in predictions if item.is_hallucination is not None
    }
    truth_map = {item.id: item for item in truths}
    common_ids = sorted(prediction_map.keys() & truth_map.keys())
    tp = tn = fp = fn = 0
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    positive_count = 0
    primary_hits = 0
    multilabel_hits = 0
    category_totals: Counter[str] = Counter()
    category_hits: Counter[str] = Counter()

    for item_id in common_ids:
        prediction = prediction_map[item_id]
        truth = truth_map[item_id]
        predicted = bool(prediction.is_hallucination)
        actual = truth.is_hallucination
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
            false_positive_ids.append(item_id)
        elif not predicted and actual:
            fn += 1
            false_negative_ids.append(item_id)
        else:
            tn += 1
        if actual and truth.hallucination_type:
            expected = TYPE_MAPPING.get(truth.hallucination_type, truth.hallucination_type)
            positive_count += 1
            category_totals[expected] += 1
            if prediction.primary_category == expected:
                primary_hits += 1
            if expected in prediction.category_names:
                multilabel_hits += 1
                category_hits[expected] += 1

    return {
        "evaluated_count": len(common_ids),
        "ground_truth_count": len(truths),
        "prediction_count": len(prediction_map),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": _divide(tp, tp + fp),
        "recall": _divide(tp, tp + fn),
        "f1": _divide(2 * tp, 2 * tp + fp + fn),
        "accuracy": _divide(tp + tn, len(common_ids)),
        "false_positive_ids": false_positive_ids,
        "false_negative_ids": false_negative_ids,
        "missing_prediction_ids": sorted(truth_map.keys() - prediction_map.keys()),
        "unmatched_prediction_ids": sorted(prediction_map.keys() - truth_map.keys()),
        "primary_category_accuracy": _divide(primary_hits, positive_count),
        "multilabel_category_hit_rate": _divide(multilabel_hits, positive_count),
        "category_stats": {
            name: {
                "expected": count,
                "matched": category_hits[name],
                "hit_rate": _divide(category_hits[name], count),
            }
            for name, count in sorted(category_totals.items())
        },
    }

