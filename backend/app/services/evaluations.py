import json
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import (
    Category,
    CategorySuggestion,
    DetectionItem,
    DetectionTask,
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


def record_evaluation_progress(
    session: Session,
    evaluation: Evaluation,
    stage: str,
    progress: int,
    *,
    status: str | None = None,
) -> None:
    """持久化可向用户公开的业务阶段，供 SSE 断线重连后继续读取。"""
    events = list(evaluation.insight_events or [])
    events.append(
        {
            "sequence": len(events) + 1,
            "stage": stage,
            "progress": max(0, min(100, progress)),
            "status": status or evaluation.insight_status,
            "created_at": utc_now().isoformat(),
        }
    )
    evaluation.insight_stage = stage[:200]
    evaluation.insight_progress = max(0, min(100, progress))
    evaluation.insight_events = events
    if status:
        evaluation.insight_status = status
    session.commit()


async def run_evaluation_insights(evaluation_id: str) -> None:
    """使用独立会话执行响应返回后的评测分析。"""
    with SessionLocal() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        if evaluation is None:
            return
        predictions = list(
            session.scalars(
                select(DetectionItem).where(DetectionItem.task_id == evaluation.task_id)
            )
        )
        truths = [GroundTruthItem.model_validate(item) for item in evaluation.ground_truth_snapshot]
        try:
            await create_evaluation_insights(session, evaluation, predictions, truths)
        except Exception as exc:
            evaluation.insight_error = f"后台评测失败: {exc}"[:2000]
            record_evaluation_progress(
                session,
                evaluation,
                "误判分析失败，请查看错误信息后重试",
                100,
                status="fallback",
            )


def _divide(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def validate_ground_truth_ids(
    predictions: list[DetectionItem], truths: list[GroundTruthItem]
) -> None:
    prediction_ids = {item.input_id for item in predictions}
    truth_ids = {item.id for item in truths}
    missing = sorted(prediction_ids - truth_ids)
    unknown = sorted(truth_ids - prediction_ids)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"缺少任务 ID：{'、'.join(missing[:10])}")
        if unknown:
            details.append(f"包含未知 ID：{'、'.join(unknown[:10])}")
        raise ValueError("人工标注必须与任务条目完全一致；" + "；".join(details))


def calculate_metrics(
    predictions: list[DetectionItem], truths: list[GroundTruthItem]
) -> dict[str, object]:
    prediction_map = {
        item.input_id: item for item in predictions if item.is_hallucination is not None
    }
    truth_map = {item.id: item for item in truths}
    all_truth_ids = sorted(truth_map)
    tp = tn = fp = fn = 0
    binary_tp = binary_tn = binary_fp = binary_fn = 0
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    category_mismatch_ids: list[str] = []
    category_mismatches: list[dict[str, object]] = []

    for item_id in all_truth_ids:
        truth = truth_map[item_id]
        prediction = prediction_map.get(item_id)
        if prediction is None:
            # 未产出模型判定不能被静默排除，否则部分失败任务会得到虚高的检出率。
            if truth.is_hallucination:
                fn += 1
                binary_fn += 1
                false_negative_ids.append(item_id)
            continue
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
        "evaluated_count": len(truths),
        "ground_truth_count": len(truths),
        "prediction_count": len(prediction_map),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": _divide(tp, tp + fp),
        "recall": _divide(tp, tp + fn),
        "accuracy": _divide(tp + tn, len(truths)),
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


def build_category_performance(
    predictions: list[DetectionItem], truths: list[GroundTruthItem]
) -> list[dict[str, object]]:
    """汇总分类的正确使用和误选情况，防止优化建议误删仍然有效的分类。"""
    truth_map = {item.id: item for item in truths}
    performance: dict[str, dict[str, object]] = {}
    for prediction in predictions:
        truth = truth_map.get(prediction.input_id)
        if truth is None or prediction.is_hallucination is None:
            continue
        predicted_name = prediction.primary_category if prediction.is_hallucination else "正常"
        expected_name = truth.hallucination_type if truth.is_hallucination else "正常"
        predicted_name = predicted_name or "未分类"
        expected_name = expected_name or "未分类"
        stats = performance.setdefault(
            predicted_name,
            {
                "category_name": predicted_name,
                "predicted_count": 0,
                "correct_count": 0,
                "mismatches": [],
            },
        )
        stats["predicted_count"] = cast(int, stats["predicted_count"]) + 1
        if predicted_name == expected_name:
            stats["correct_count"] = cast(int, stats["correct_count"]) + 1
        else:
            mismatches = cast(list[dict[str, str]], stats["mismatches"])
            mismatches.append(
                {
                    "input_id": prediction.input_id,
                    "expected_category": expected_name,
                }
            )
    return sorted(performance.values(), key=lambda item: str(item["category_name"]))


def _round_snapshot(
    evaluation: Evaluation,
    predictions: list[DetectionItem],
) -> dict[str, object]:
    """构造一轮评测的紧凑快照，供跨轮趋势分析而非重新调用检测模型。"""
    truths = [GroundTruthItem.model_validate(item) for item in evaluation.ground_truth_snapshot]
    truth_map = {item.id: item for item in truths}
    prediction_map = {item.input_id: item for item in predictions}
    comparisons: list[dict[str, object]] = []
    for input_id, truth in sorted(truth_map.items()):
        prediction = prediction_map.get(input_id)
        expected = truth.hallucination_type if truth.is_hallucination else "正常"
        if prediction is None or prediction.is_hallucination is None:
            predicted = "未产出"
        elif prediction.is_hallucination:
            predicted = prediction.primary_category or "未分类"
        else:
            predicted = "正常"
        comparisons.append(
            {
                "input_id": input_id,
                "expected_category": expected or "未分类",
                "predicted_category": predicted,
                "is_correct": predicted == (expected or "未分类"),
            }
        )
    return {
        "evaluation_id": evaluation.id,
        "task_id": evaluation.task_id,
        "accuracy": evaluation.metrics.get("accuracy", 0),
        "created_at": evaluation.created_at.isoformat(),
        "comparisons": comparisons,
    }


def build_optimization_context(
    session: Session,
    evaluation: Evaluation,
    predictions: list[DetectionItem],
    truths: list[GroundTruthItem],
    categories: list[Category],
    settings: Settings | None = None,
) -> dict[str, object]:
    """汇总同一知识库最近轮次，避免建议只针对当前误判做局部修补。"""
    active_settings = settings or get_settings()
    current_task = session.get(DetectionTask, evaluation.task_id)
    prior_evaluations: list[Evaluation] = []
    target_input_ids = {item.id for item in truths}
    if current_task is not None:
        candidates = list(
            session.scalars(
                select(Evaluation)
                .join(DetectionTask, Evaluation.task_id == DetectionTask.id)
                .where(
                    Evaluation.id != evaluation.id,
                    Evaluation.task_id != evaluation.task_id,
                    Evaluation.created_at < evaluation.created_at,
                    DetectionTask.knowledge_base_id == current_task.knowledge_base_id,
                )
                .order_by(Evaluation.created_at.desc())
                .limit(30)
            )
        )
        seen_task_ids: set[str] = set()
        for candidate in candidates:
            if candidate.task_id in seen_task_ids:
                continue
            candidate_ids = {str(item.get("id")) for item in candidate.ground_truth_snapshot or []}
            if candidate_ids == target_input_ids:
                prior_evaluations.append(candidate)
                seen_task_ids.add(candidate.task_id)
            if len(prior_evaluations) == active_settings.evaluation_history_rounds:
                break
    prior_evaluations.reverse()
    rounds: list[dict[str, object]] = []
    for prior in prior_evaluations:
        prior_predictions = list(
            session.scalars(select(DetectionItem).where(DetectionItem.task_id == prior.task_id))
        )
        rounds.append(_round_snapshot(prior, prior_predictions))
    rounds.append(_round_snapshot(evaluation, predictions))

    recurring: dict[tuple[str, str], dict[str, object]] = {}
    lifetime: dict[str, dict[str, object]] = {}
    for round_data in rounds:
        seen_pairs: set[tuple[str, str]] = set()
        for comparison in cast(list[dict[str, object]], round_data["comparisons"]):
            predicted = str(comparison["predicted_category"])
            expected = str(comparison["expected_category"])
            if predicted not in {"正常", "未产出", "未分类"}:
                stats = lifetime.setdefault(
                    predicted,
                    {
                        "category_name": predicted,
                        "predicted_count": 0,
                        "correct_count": 0,
                        "mismatch_count": 0,
                    },
                )
                stats["predicted_count"] = cast(int, stats["predicted_count"]) + 1
                key = "correct_count" if comparison["is_correct"] else "mismatch_count"
                stats[key] = cast(int, stats[key]) + 1
            if comparison["is_correct"]:
                continue
            pair = recurring.setdefault(
                (expected, predicted),
                {
                    "expected_category": expected,
                    "predicted_category": predicted,
                    "round_count": 0,
                    "case_ids": [],
                },
            )
            if (expected, predicted) not in seen_pairs:
                pair["round_count"] = cast(int, pair["round_count"]) + 1
                seen_pairs.add((expected, predicted))
            case_ids = cast(list[str], pair["case_ids"])
            input_id = str(comparison["input_id"])
            if input_id not in case_ids and len(case_ids) < 10:
                case_ids.append(input_id)

    regressions: list[dict[str, object]] = []
    if len(rounds) >= 2:
        previous = {
            str(item["input_id"]): item
            for item in cast(list[dict[str, object]], rounds[-2]["comparisons"])
        }
        for current in cast(list[dict[str, object]], rounds[-1]["comparisons"]):
            old = previous.get(str(current["input_id"]))
            if old and old["is_correct"] and not current["is_correct"]:
                regressions.append(
                    {
                        "input_id": current["input_id"],
                        "previous_prediction": old["predicted_category"],
                        "current_prediction": current["predicted_category"],
                        "expected_category": current["expected_category"],
                    }
                )

    target_names = sorted(
        {
            item.hallucination_type
            for item in truths
            if item.is_hallucination and item.hallucination_type
        }
    )
    category_conflicts: list[dict[str, str]] = []
    for index, left in enumerate(categories):
        for right in categories[index + 1 :]:
            left_definition = " ".join((left.description + " " + left.prompt_guidance).split())
            right_definition = " ".join((right.description + " " + right.prompt_guidance).split())
            if left_definition and left_definition == right_definition:
                category_conflicts.append(
                    {
                        "left_category": left.name,
                        "right_category": right.name,
                        "conflict_type": "定义与判断指引完全相同",
                    }
                )

    applied_history: list[tuple[CategorySuggestion, Evaluation]] = []
    historical_evaluation_ids = [item.id for item in prior_evaluations]
    if historical_evaluation_ids:
        applied_history = list(
            session.execute(
                select(CategorySuggestion, Evaluation)
                .join(Evaluation, CategorySuggestion.evaluation_id == Evaluation.id)
                .join(DetectionTask, Evaluation.task_id == DetectionTask.id)
                .where(
                    CategorySuggestion.status == "applied",
                    Evaluation.id.in_(historical_evaluation_ids),
                )
                .order_by(Evaluation.created_at.desc())
                .limit(15)
            ).tuples()
        )
    context: dict[str, object] = {
        "history_round_count": len(rounds),
        "target_taxonomy_names": target_names,
        "evaluation_history": [
            {
                "evaluation_id": item["evaluation_id"],
                "task_id": item["task_id"],
                "accuracy": item["accuracy"],
                "created_at": item["created_at"],
            }
            for item in rounds
        ],
        "recurring_mismatches": sorted(
            recurring.values(), key=lambda item: cast(int, item["round_count"]), reverse=True
        )[:20],
        "regression_cases": regressions[:20],
        "category_lifetime_performance": sorted(
            lifetime.values(), key=lambda item: str(item["category_name"])
        ),
        "category_conflicts": category_conflicts,
        "applied_suggestion_history": [
            {
                "evaluation_id": historical_evaluation.id,
                "action": suggestion.action,
                "target_category_name": suggestion.target_category_name,
                "proposed_changes": {
                    key: (value[:300] if isinstance(value, str) else value)
                    for key, value in suggestion.proposed_changes.items()
                },
            }
            for suggestion, historical_evaluation in applied_history
        ],
        "detector_rules": {
            "comparison": "人工分类与模型主分类名称必须完全一致，不允许映射",
            "mode": "单标签",
            "selection": "优先选择最具体且直接覆盖核心错误的分类",
        },
        "context_limits": {
            "history_rounds": active_settings.evaluation_history_rounds,
            "max_chars": active_settings.evaluation_context_max_chars,
        },
    }
    return _trim_optimization_context(context, active_settings.evaluation_context_max_chars)


def _trim_optimization_context(context: dict[str, object], max_chars: int) -> dict[str, object]:
    """按价值从低到高裁剪历史摘要，避免优化提示词随轮次无限增长。"""
    trimmed = dict(context)
    list_fields = (
        "evaluation_history",
        "recurring_mismatches",
        "regression_cases",
        "category_lifetime_performance",
        "category_conflicts",
        "applied_suggestion_history",
    )
    for field in list_fields:
        trimmed[field] = list(cast(list[object], context.get(field, [])))

    def size() -> int:
        return len(json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")))

    while size() > max_chars:
        applied = cast(list[object], trimmed["applied_suggestion_history"])
        conflicts = cast(list[object], trimmed["category_conflicts"])
        recurring = cast(list[object], trimmed["recurring_mismatches"])
        history = cast(list[object], trimmed["evaluation_history"])
        regressions = cast(list[object], trimmed["regression_cases"])
        lifetime = cast(list[object], trimmed["category_lifetime_performance"])
        if applied:
            applied.pop()
        elif conflicts:
            conflicts.pop()
        elif len(recurring) > 3:
            recurring.pop()
        elif len(history) > 1:
            history.pop(0)
        elif len(regressions) > 5:
            regressions.pop()
        elif lifetime:
            lifetime.pop()
        else:
            break
    limits = cast(dict[str, object], trimmed["context_limits"])
    serialized_chars = size()
    limits["serialized_chars"] = serialized_chars
    limits["truncated"] = serialized_chars > max_chars or any(
        len(cast(list[object], trimmed[field])) < len(cast(list[object], context.get(field, [])))
        for field in list_fields
    )
    limits["serialized_chars"] = size()
    return trimmed


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
    record_evaluation_progress(
        session,
        evaluation,
        "指标计算完成，正在识别漏检和误报",
        20,
        status="running",
    )
    error_cases = build_error_cases(predictions, truths, evaluation.metrics)
    if not error_cases:
        evaluation.insight_error = None
        record_evaluation_progress(
            session,
            evaluation,
            "未发现漏检或误报，比较完成",
            100,
            status="completed",
        )
        return
    record_evaluation_progress(
        session,
        evaluation,
        f"发现 {len(error_cases)} 条误判，正在准备分析上下文",
        35,
    )
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
    category_performance = build_category_performance(predictions, truths)
    optimization_context = build_optimization_context(
        session,
        evaluation,
        predictions,
        truths,
        categories,
    )
    evaluation.optimization_context = optimization_context
    session.commit()
    generated = EvaluationAnalysisResponse(analyses=[], suggestions=[])
    analysis_succeeded = False
    try:
        generated = await DeepSeekClient().analyze_evaluation(
            error_cases,
            category_payload,
            category_performance=category_performance,
            optimization_context=optimization_context,
            progress_callback=lambda stage, progress: record_evaluation_progress(
                session, evaluation, stage, progress
            ),
        )
        analysis_succeeded = True
        evaluation.insight_error = None
    except DeepSeekError as exc:
        evaluation.insight_error = str(exc)[:2000]
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
        impact_analysis = {
            "resolved_mismatch_pairs": suggestion_draft.resolved_mismatch_pairs,
            "resolved_case_ids": suggestion_draft.resolved_case_ids,
            "historical_evidence": suggestion_draft.historical_evidence,
            "regression_risk": suggestion_draft.regression_risk,
            "regression_risk_reason": suggestion_draft.regression_risk_reason,
        }
        session.add(
            CategorySuggestion(
                evaluation_id=evaluation.id,
                category_id=category.id if category else None,
                action=suggestion_draft.action,
                target_category_name=suggestion_draft.target_category_name,
                reason=suggestion_draft.reason,
                proposed_changes=changes,
                impact_analysis=impact_analysis,
            )
        )
    session.commit()
    if analysis_succeeded:
        record_evaluation_progress(
            session,
            evaluation,
            f"已保存 {len(error_cases)} 条误判分析和 {len(generated.suggestions)} 条优化建议",
            100,
            status="completed",
        )
    else:
        record_evaluation_progress(
            session,
            evaluation,
            "AI 优化建议生成失败，已保存规则化误判分析",
            100,
            status="fallback",
        )


def _apply_suggestion_change(session: Session, suggestion: CategorySuggestion) -> None:
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
        return

    target_category = session.get(Category, suggestion.category_id)
    if target_category is None or target_category.is_archived:
        raise LookupError("目标幻觉分类不存在或已归档")
    ensure_category_version(session, target_category, commit=False)
    if suggestion.action == "archive":
        target_category.is_archived = True
        target_category.is_active = False
        note = f"采纳评测归档建议 {suggestion.id}"
    else:
        for field, value in suggestion.proposed_changes.items():
            if field in {"name", "description", "prompt_guidance", "default_severity"}:
                setattr(target_category, field, value)
        note = f"采纳评测修改建议 {suggestion.id}"
    target_category.updated_at = utc_now()
    record_category_version(
        session,
        target_category,
        source="evaluation_suggestion",
        note=note,
    )


def decide_suggestion(
    session: Session, suggestion: CategorySuggestion, *, apply: bool
) -> CategorySuggestion:
    if suggestion.status != "pending":
        raise ValueError("该优化建议已经处理")
    try:
        if apply:
            _apply_suggestion_change(session, suggestion)
            suggestion.status = "applied"
        else:
            suggestion.status = "rejected"
        suggestion.decided_at = utc_now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(suggestion)
    return suggestion


def decide_suggestion_plan(
    session: Session, evaluation: Evaluation, *, apply: bool
) -> list[CategorySuggestion]:
    suggestions = list(evaluation.suggestions)
    if not suggestions:
        raise ValueError("当前评测没有优化建议")
    if any(item.status != "pending" for item in suggestions):
        raise ValueError("该优化方案已部分或全部处理，不能再整套操作")
    try:
        for suggestion in suggestions:
            if apply:
                _apply_suggestion_change(session, suggestion)
                suggestion.status = "applied"
            else:
                suggestion.status = "rejected"
            suggestion.decided_at = utc_now()
        session.commit()
    except Exception:
        session.rollback()
        raise
    for suggestion in suggestions:
        session.refresh(suggestion)
    return suggestions
