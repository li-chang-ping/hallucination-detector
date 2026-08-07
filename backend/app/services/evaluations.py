from contextlib import suppress
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Category,
    CategorySuggestion,
    DetectionItem,
    Evaluation,
    EvaluationAnalysis,
    utc_now,
)
from app.schemas.evaluations import (
    EvaluationAnalysisDraft,
    EvaluationAnalysisResponse,
    GroundTruthItem,
)
from app.services.categories import ensure_category_version, record_category_version
from app.services.deepseek import DeepSeekClient, DeepSeekError


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
    binary_tp = binary_tn = binary_fp = binary_fn = 0
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    category_mismatch_ids: list[str] = []
    category_mismatches: list[dict[str, object]] = []

    for item_id in common_ids:
        prediction = prediction_map[item_id]
        truth = truth_map[item_id]
        predicted = bool(prediction.is_hallucination)
        actual = truth.is_hallucination
        expected = truth.hallucination_type if actual and truth.hallucination_type else None
        category_mismatch = bool(
            predicted and actual and expected and expected != prediction.primary_category
        )

        # 保留标准二分类矩阵，同时按业务口径将分类未命中计入对外展示的误报。
        if predicted and actual:
            binary_tp += 1
        elif predicted and not actual:
            binary_fp += 1
        elif not predicted and actual:
            binary_fn += 1
        else:
            binary_tn += 1

        if category_mismatch:
            fp += 1
            false_positive_ids.append(item_id)
            category_mismatch_ids.append(item_id)
            category_mismatches.append(
                {
                    "id": item_id,
                    "expected_category": expected,
                    "predicted_category": prediction.primary_category,
                }
            )
        elif predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
            false_positive_ids.append(item_id)
        elif not predicted and actual:
            fn += 1
            false_negative_ids.append(item_id)
        else:
            tn += 1
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
        "accuracy": _divide(tp + tn, len(common_ids)),
        "false_positive_ids": false_positive_ids,
        "false_negative_ids": false_negative_ids,
        "category_mismatch_ids": category_mismatch_ids,
        "category_mismatches": category_mismatches,
        "binary_confusion_matrix": {
            "tp": binary_tp,
            "tn": binary_tn,
            "fp": binary_fp,
            "fn": binary_fn,
        },
        "missing_prediction_ids": sorted(truth_map.keys() - prediction_map.keys()),
        "unmatched_prediction_ids": sorted(prediction_map.keys() - truth_map.keys()),
    }


def _expected_category(truth: GroundTruthItem) -> str | None:
    if not truth.is_hallucination or not truth.hallucination_type:
        return None
    return truth.hallucination_type


def build_error_cases(
    predictions: list[DetectionItem],
    truths: list[GroundTruthItem],
    metrics: dict[str, object],
) -> list[dict[str, object]]:
    prediction_map = {item.input_id: item for item in predictions}
    truth_map = {item.id: item for item in truths}
    false_negative_ids = set(cast(list[str], metrics["false_negative_ids"]))
    false_positive_ids = set(cast(list[str], metrics["false_positive_ids"]))
    cases: list[dict[str, object]] = []
    for input_id in sorted(false_negative_ids | false_positive_ids):
        prediction = prediction_map[input_id]
        truth = truth_map[input_id]
        cases.append(
            {
                "input_id": input_id,
                "error_type": (
                    "false_negative" if input_id in false_negative_ids else "false_positive"
                ),
                "human_category": _expected_category(truth),
                "predicted_category": prediction.primary_category,
                "human_detail": truth.detail,
                "user_question": prediction.user_question,
                "system_reply": prediction.system_reply,
                "model_rationale": prediction.rationale,
                "evidence": prediction.evidence_snapshot,
            }
        )
    return cases


def _fallback_analysis(case: dict[str, object]) -> tuple[str, str]:
    if case["error_type"] == "false_negative":
        reason = f"人工标注为“{case['human_category']}”，模型判定为正常，因此构成漏检。"
        cause = "模型可能未识别回复与证据的冲突，或当前分类判定指引对该边界描述不足。"
    elif case["human_category"] is None:
        reason = f"人工标注为正常，模型判定为“{case['predicted_category']}”，因此构成误报。"
        cause = "模型可能把证据未明确覆盖的信息过度解释为幻觉。"
    else:
        reason = (
            f"人工分类为“{case['human_category']}”，模型分类为“{case['predicted_category']}”，"
            "分类不一致，按当前业务口径计为误报。"
        )
        cause = (
            "人工标注与模型使用的分类名称不同；系统按要求不做任何映射，"
            "因此即使语义接近也会计为分类不一致。"
        )
    return reason, cause


async def create_evaluation_insights(
    session: Session,
    evaluation: Evaluation,
    predictions: list[DetectionItem],
    truths: list[GroundTruthItem],
) -> None:
    error_cases = build_error_cases(predictions, truths, evaluation.metrics)
    if not error_cases:
        return
    categories = list(session.scalars(select(Category).where(Category.is_archived.is_(False))))
    category_payload: list[dict[str, object]] = [
        {
            "name": item.name,
            "description": item.description,
            "default_severity": item.default_severity,
            "prompt_guidance": item.prompt_guidance,
        }
        for item in categories
    ]
    generated = EvaluationAnalysisResponse(analyses=[], suggestions=[])
    with suppress(DeepSeekError):
        generated = await DeepSeekClient().analyze_evaluation(error_cases, category_payload)
    # 分析属于增强能力，失败时不能让已经完成的人工评测回滚。
    generated_map: dict[tuple[str, str], object] = {
        (item.input_id, item.error_type): item for item in generated.analyses
    }
    for case in error_cases:
        key = (str(case["input_id"]), str(case["error_type"]))
        analysis_draft = generated_map.get(key)
        fallback_reason, fallback_cause = _fallback_analysis(case)
        session.add(
            EvaluationAnalysis(
                evaluation_id=evaluation.id,
                input_id=key[0],
                error_type=key[1],
                human_category=cast(str | None, case["human_category"]),
                predicted_category=cast(str | None, case["predicted_category"]),
                # 误报/漏检口径由指标代码确定，不能让模型重新解释或改写人工标签。
                reason=fallback_reason,
                likely_cause=fallback_cause,
                evidence_summary=(
                    cast(EvaluationAnalysisDraft, analysis_draft).evidence_summary
                    if analysis_draft
                    else ""
                ),
            )
        )
    category_map = {item.name: item for item in categories}
    for suggestion_draft in generated.suggestions:
        category = category_map.get(suggestion_draft.target_category_name)
        changes = {
            key.removeprefix("proposed_"): value
            for key, value in suggestion_draft.model_dump(mode="json").items()
            if key.startswith("proposed_") and value is not None
        }
        session.add(
            CategorySuggestion(
                evaluation_id=evaluation.id,
                category_id=category.id if category else None,
                action=suggestion_draft.action,
                target_category_name=suggestion_draft.target_category_name,
                reason=suggestion_draft.reason,
                proposed_changes=changes,
            )
        )
    session.commit()


def decide_suggestion(
    session: Session, suggestion: CategorySuggestion, *, apply: bool
) -> CategorySuggestion:
    if suggestion.status != "pending":
        raise ValueError("该优化建议已经处理")
    if apply:
        if suggestion.action == "create":
            changes = suggestion.proposed_changes
            category = Category(
                name=suggestion.target_category_name,
                description=cast(str, changes["description"]),
                default_severity=cast(str, changes["default_severity"]),
                prompt_guidance=cast(str, changes.get("prompt_guidance", "")),
                is_active=True,
            )
            session.add(category)
            session.flush()
            suggestion.category_id = category.id
            record_category_version(
                session,
                category,
                source="evaluation_suggestion",
                note=f"采纳评测新增建议 {suggestion.id}",
            )
        else:
            target_category = session.get(Category, suggestion.category_id)
            if target_category is None or target_category.is_archived:
                raise LookupError("目标幻觉分类不存在或已归档")
            ensure_category_version(session, target_category)
            if suggestion.action == "archive":
                target_category.is_archived = True
                target_category.is_active = False
                note = f"采纳评测归档建议 {suggestion.id}"
            else:
                for field, value in suggestion.proposed_changes.items():
                    if field in {
                        "name",
                        "description",
                        "prompt_guidance",
                        "default_severity",
                    }:
                        setattr(target_category, field, value)
                note = f"采纳评测修改建议 {suggestion.id}"
            target_category.updated_at = utc_now()
            record_category_version(
                session,
                target_category,
                source="evaluation_suggestion",
                note=note,
            )
        suggestion.status = "applied"
    else:
        suggestion.status = "rejected"
    suggestion.decided_at = utc_now()
    session.commit()
    session.refresh(suggestion)
    return suggestion
