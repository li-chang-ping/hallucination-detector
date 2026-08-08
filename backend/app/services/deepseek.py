import asyncio
import json
from collections.abc import Callable
from typing import Any, cast

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas.evaluations import EvaluationAnalysisResponse
from app.schemas.tasks import DetectionDecision


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def detect(
        self,
        user_question: str,
        system_reply: str,
        evidence: list[dict[str, object]],
        categories: list[dict[str, object]],
    ) -> tuple[DetectionDecision, dict[str, int]]:
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("未配置 DEEPSEEK_API_KEY")
        allowed_names = {str(item["name"]) for item in categories}
        prompt = self._build_prompt(user_question, system_reply, evidence, categories)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(
                        f"{self.settings.deepseek_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                        json={
                            "model": self.settings.deepseek_model,
                            "messages": [
                                {"role": "system", "content": self._system_prompt()},
                                {"role": "user", "content": prompt},
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0,
                            "max_tokens": 1200,
                            "thinking": {"type": "disabled"},
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    content = payload["choices"][0]["message"]["content"]
                    if not content:
                        raise ValueError("模型返回空内容")
                    decision = DetectionDecision.model_validate_json(content)
                    unknown = set(decision.category_names) - allowed_names
                    if unknown:
                        raise ValueError(f"模型返回未知分类: {', '.join(sorted(unknown))}")
                    usage = payload.get("usage") or {}
                    return decision, {
                        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                        "completion_tokens": int(usage.get("completion_tokens", 0)),
                    }
            except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise DeepSeekError(f"DeepSeek 连续三次调用失败: {last_error}") from last_error

    async def analyze_evaluation(
        self,
        error_cases: list[dict[str, object]],
        categories: list[dict[str, object]],
        category_performance: list[dict[str, object]] | None = None,
        optimization_context: dict[str, object] | None = None,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> EvaluationAnalysisResponse:
        """分析已由确定性指标识别出的误判，不允许模型改写误判清单。"""
        if not self.settings.deepseek_api_key:
            raise DeepSeekError("未配置 DEEPSEEK_API_KEY")
        allowed_names = {str(item["name"]) for item in categories}
        missing_names = {
            str(item["human_category"])
            for item in error_cases
            if item.get("human_category") and str(item["human_category"]) not in allowed_names
        }
        context = optimization_context or {}
        target_names = {
            str(name) for name in cast(list[object], context.get("target_taxonomy_names", []))
        }
        human_names = {
            str(item["human_category"]) for item in error_cases if item.get("human_category")
        } | target_names
        existing_human_names = human_names & allowed_names
        migration_sources = {
            str(item["predicted_category"])
            for item in error_cases
            if item.get("predicted_category")
            and item.get("human_category")
            and str(item["human_category"]) in missing_names
        }
        performance = category_performance or []
        lifetime_performance = cast(
            list[dict[str, object]], context.get("category_lifetime_performance", [])
        )
        protected_names = (
            target_names
            | existing_human_names
            | {
                str(item["category_name"])
                for item in performance + lifetime_performance
                if item.get("category_name") not in {None, "正常", "未分类"}
                and cast(int, item.get("correct_count", 0)) > 0
            }
        )
        recurring = cast(list[dict[str, object]], context.get("recurring_mismatches", []))
        obsolete_sources = {
            str(item["predicted_category"])
            for item in recurring
            if cast(int, item.get("round_count", 0)) >= 2
            and str(item.get("expected_category")) in target_names
            and str(item.get("predicted_category")) not in target_names
            and str(item.get("predicted_category")) in allowed_names
            and next(
                (
                    cast(int, stats.get("correct_count", 0))
                    for stats in lifetime_performance
                    if str(stats.get("category_name")) == str(item.get("predicted_category"))
                ),
                0,
            )
            == 0
        }
        payload_data = {
            "error_cases": error_cases,
            "current_categories": categories,
            "category_performance": performance,
            "optimization_context": context,
            "evaluation_rule": (
                "人工分类与模型分类按名称完全一致比较，不允许任何映射；"
                "名称不同即使语义接近也计为误报。"
            ),
            "missing_human_category_names": sorted(missing_names),
            "existing_human_category_names": sorted(existing_human_names),
            "protected_category_names": sorted(protected_names),
            "migration_source_category_names": sorted(migration_sources),
            "obsolete_recurring_category_names": sorted(obsolete_sources),
            "boundary_mismatches": [
                {
                    "input_id": item.get("input_id"),
                    "predicted_category": item.get("predicted_category"),
                    "human_category": item.get("human_category"),
                }
                for item in error_cases
                if item.get("predicted_category")
                and item.get("human_category")
                and item["predicted_category"] != item["human_category"]
            ],
            "output_json_schema": EvaluationAnalysisResponse.model_json_schema(),
            "requirements": [
                "逐条解释误判形成原因，analysis 的 input_id 和 error_type 必须与输入一致",
                "只在分类边界或判定指引确实可改进时给出建议，避免为单个样本过拟合",
                "建议 action 可为 create、update、archive",
                "create 用于缺少必要分类，target_category_name 是新分类名",
                "update 可修改 name、description、prompt_guidance、default_severity",
                "archive 仅用于确认冗余或错误的现有分类，不包含 proposed 字段",
                "先查看 category_performance；correct_count 大于 0 表示该分类仍有正确用途，"
                "不得因少量误选而删除或改名",
                "existing_human_category_names 中的分类是需要保留的人工标准分类，不得归档，"
                "也不得将其反向重命名为模型误选的分类",
                "protected_category_names 中的分类不得 archive 或修改 name；"
                "可以 update description 和 prompt_guidance 来澄清与相邻分类的边界",
                "结合 optimization_context 的历轮准确率、反复错配、回退样本和已采纳建议判断，"
                "不得重复给出已被证明无效的同类修改",
                "当人工分类和模型分类都已存在时，先判断是边界含混还是冗余旧分类；"
                "边界含混可 update，零正确命中且跨轮持续抢占目标分类的旧分类应 archive",
                "只有人工分类名称缺失时才属于结构迁移；创建缺失分类后，必须归档、重命名或"
                "更新 migration_source_category_names 中旧分类的边界，避免旧定义继续误选",
                "名称一对一不一致且目标名称尚不存在时，才可用 update 修改 name",
                "现有宽泛分类对应多个人工分类时，必须 create 每个缺失的人工同名分类",
                "名称都已存在时，修改描述或指引的目标是让下一轮模型选择正确的已有名称",
                "obsolete_recurring_category_names 是无正确用途且跨轮持续误选的旧分类，"
                "必须归档或重命名，不能仅修改描述或判断指引后继续保留",
                "target_taxonomy_names 是本批人工标注的完整目标分类集合，不得归档或改名",
                "每条建议必须给出 resolved_mismatch_pairs、resolved_case_ids、historical_evidence、"
                "regression_risk 和 regression_risk_reason，明确收益依据及回归风险",
                "同一个目标名称只能选择 create 或重命名其中一种，不得生成冲突建议",
                "把全部 suggestions 作为一套原子执行的分类迁移方案，不得包含互相冲突的操作",
                "一对一名称替换应 update 旧分类名称，不要 create 语义相同的新分类",
                "一个宽泛旧分类拆为多个人工细分类时，必须 create 缺失细分类；"
                "旧分类 correct_count 为 0 时可 archive，仍有正确命中时必须保留并 update 边界",
                "不得把分类重命名为任何已有分类名称，也不得让多个分类重命名为同一名称",
                "存在误判时至少给出一条可执行的分类优化建议",
                "不要输出思维过程",
            ],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是客服幻觉评测专家。输出 JSON 对象，字段仅为 "
                    "analyses 和 suggestions。建议必须改善分类边界，"
                    "且保持通用性。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload_data, ensure_ascii=False),
            },
        ]
        last_error: Exception | None = None
        for attempt in range(3):
            content: str | None = None
            try:
                if progress_callback:
                    progress_callback(
                        f"正在请求 DeepSeek 生成误判分析与优化建议（第 {attempt + 1}/3 次）",
                        45 + attempt * 15,
                    )
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(
                        f"{self.settings.deepseek_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                        json={
                            "model": self.settings.deepseek_model,
                            "messages": messages,
                            "response_format": {"type": "json_object"},
                            "temperature": 0,
                            "max_tokens": 6000,
                            "thinking": {"type": "disabled"},
                        },
                    )
                    response.raise_for_status()
                    raw_content = response.json()["choices"][0]["message"]["content"]
                    if not isinstance(raw_content, str) or not raw_content:
                        raise ValueError("模型返回空内容或非文本内容")
                    content = raw_content
                    if progress_callback:
                        progress_callback(
                            "DeepSeek 已返回结果，正在校验完整优化方案",
                            52 + attempt * 15,
                        )
                    result = EvaluationAnalysisResponse.model_validate_json(content)
                    expected_cases = {
                        (str(item["input_id"]), str(item["error_type"])) for item in error_cases
                    }
                    actual_cases = {(item.input_id, item.error_type) for item in result.analyses}
                    missing_cases = expected_cases - actual_cases
                    if missing_cases:
                        missing_ids = ", ".join(sorted(item_id for item_id, _ in missing_cases))
                        raise ValueError(f"缺少误判分析: {missing_ids}")
                    self._validate_suggestions(
                        result,
                        allowed_names,
                        missing_names,
                        migration_sources=migration_sources,
                        protected_names=protected_names,
                        obsolete_sources=obsolete_sources,
                    )
                    if progress_callback:
                        progress_callback("优化方案校验通过，正在保存结果", 92)
                    return result
            except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
                last_error = exc
                if attempt < 2:
                    if progress_callback:
                        detail = str(exc) if content is not None else "DeepSeek 请求失败"
                        progress_callback(
                            f"第 {attempt + 1} 次结果未通过：{detail}；正在修正并重试",
                            min(58 + attempt * 15, 88),
                        )
                    if content is not None:
                        messages.extend(
                            [
                                {"role": "assistant", "content": content},
                                {
                                    "role": "user",
                                    "content": self._build_evaluation_correction(
                                        str(exc),
                                        existing_human_names,
                                        migration_sources,
                                        protected_names,
                                        obsolete_sources,
                                    ),
                                },
                            ]
                        )
                    await asyncio.sleep(2**attempt)
        raise DeepSeekError(f"DeepSeek 误判分析连续三次调用失败: {last_error}") from last_error

    @staticmethod
    def _build_evaluation_correction(
        validation_error: str,
        existing_human_names: set[str],
        migration_sources: set[str],
        protected_names: set[str],
        obsolete_sources: set[str],
    ) -> str:
        """将本地校验错误反馈给模型，要求修正整套建议而不是盲目重试。"""
        correction = {
            "validation_error": validation_error,
            "existing_human_category_names": sorted(existing_human_names),
            "protected_category_names": sorted(protected_names),
            "migration_source_category_names": sorted(migration_sources),
            "obsolete_recurring_category_names": sorted(obsolete_sources),
            "correction_rules": [
                "重新输出完整 JSON，不要只输出修改片段",
                "保留已存在的人工标准分类，禁止将其重命名为模型误选分类",
                "有正确命中的受保护分类不得归档或改名",
                "人工分类和模型分类都存在时，区分边界含混与冗余旧分类",
                "obsolete_recurring_category_names 必须归档或重命名，不能只更新定义",
                "只有缺失人工分类时才新增，并同步处理 migration_source_category_names",
                "不得重命名为任何现有分类名称",
                "所有 suggestions 必须构成可原子执行且无冲突的完整方案",
            ],
        }
        return "上一次输出未通过后端校验，请根据错误修正整套方案：\n" + json.dumps(
            correction, ensure_ascii=False
        )

    @staticmethod
    def _validate_suggestions(
        result: EvaluationAnalysisResponse,
        allowed_names: set[str],
        missing_names: set[str],
        *,
        migration_sources: set[str] | None = None,
        protected_names: set[str] | None = None,
        obsolete_sources: set[str] | None = None,
    ) -> None:
        if not result.suggestions:
            raise ValueError("存在误判但未返回优化建议")
        incomplete_impacts = [
            item.target_category_name
            for item in result.suggestions
            if not item.resolved_case_ids
            or not item.historical_evidence
            or not item.regression_risk_reason
        ]
        if incomplete_impacts:
            raise ValueError(
                "优化建议缺少预计改善样本、历史依据或回归风险说明: "
                + ", ".join(sorted(incomplete_impacts))
            )
        unknown = {
            item.target_category_name
            for item in result.suggestions
            if item.action in {"update", "archive"}
        } - allowed_names
        if unknown:
            raise ValueError(f"优化建议包含未知分类: {', '.join(sorted(unknown))}")
        create_names = {
            item.target_category_name for item in result.suggestions if item.action == "create"
        }
        duplicates = create_names & allowed_names
        if duplicates:
            raise ValueError(f"新增建议使用了已有分类: {', '.join(sorted(duplicates))}")
        suggestion_targets = [item.target_category_name for item in result.suggestions]
        repeated_targets = {
            name for name in suggestion_targets if suggestion_targets.count(name) > 1
        }
        if repeated_targets:
            raise ValueError(f"同一分类存在多条冲突建议: {', '.join(sorted(repeated_targets))}")
        renamed_names = {
            item.proposed_name
            for item in result.suggestions
            if item.action == "update" and item.proposed_name
        }
        conflicts = create_names & renamed_names
        if conflicts:
            raise ValueError(f"新增与重命名建议冲突: {', '.join(sorted(conflicts))}")
        existing_rename_targets = renamed_names & allowed_names
        if existing_rename_targets:
            raise ValueError(f"重命名目标已存在: {', '.join(sorted(existing_rename_targets))}")
        rename_list = [
            item.proposed_name
            for item in result.suggestions
            if item.action == "update" and item.proposed_name
        ]
        duplicate_renames = {name for name in rename_list if rename_list.count(name) > 1}
        if duplicate_renames:
            raise ValueError(f"多个分类重命名为同一名称: {', '.join(sorted(duplicate_renames))}")
        archive_names = {
            item.target_category_name for item in result.suggestions if item.action == "archive"
        }
        protected_changes = (protected_names or set()) & archive_names
        renamed_sources = {
            item.target_category_name
            for item in result.suggestions
            if item.action == "update" and item.proposed_name
        }
        protected_changes |= (protected_names or set()) & renamed_sources
        if protected_changes:
            raise ValueError(
                "仍有正确命中的分类不能归档或改名: " + ", ".join(sorted(protected_changes))
            )
        archive_rename_conflicts = archive_names & renamed_names
        if archive_rename_conflicts:
            raise ValueError(
                "归档分类不能同时作为重命名目标: " + ", ".join(sorted(archive_rename_conflicts))
            )
        unresolved = missing_names - create_names - renamed_names
        if unresolved:
            raise ValueError(f"缺少分类名称对齐建议: {', '.join(sorted(unresolved))}")
        boundary_updates = {
            item.target_category_name
            for item in result.suggestions
            if item.action == "update"
            and (item.proposed_description or item.proposed_prompt_guidance)
        }
        unresolved_sources = (
            (migration_sources or set()) - archive_names - renamed_sources - boundary_updates
        )
        if unresolved_sources:
            raise ValueError(
                "新增细分类前必须归档、重命名或更新持续误报的旧分类边界: "
                + ", ".join(sorted(unresolved_sources))
            )
        unresolved_obsolete = (
            ((obsolete_sources or set()) & allowed_names) - archive_names - renamed_sources
        )
        if unresolved_obsolete:
            raise ValueError(
                "跨轮持续误选且从未正确命中的旧分类必须归档或重命名: "
                + ", ".join(sorted(unresolved_obsolete))
            )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是严格的智能客服幻觉审计器。只能以检索证据为事实来源，不得使用常识补全。"
            "需要识别直接矛盾、无证据的肯定事实、虚假的执行能力、安全误导和实质性遗漏。"
            "当前采用单标签分类。逐项核对回复中的事实主张；存在多种问题时，先选择最具体、"
            "直接覆盖核心错误的分类，再以严重程度决胜，禁止用宽泛父类覆盖已有的精确子类。"
            "分类名称必须从允许列表原样选择，不得做同义名称映射。定义重叠时遵循判断指引中的"
            "排除条件和优先级；仍冲突时选择证据匹配最具体的分类并降低置信度。"
            "输出必须是 JSON 对象，字段为 is_hallucination、category_names、"
            "primary_category、severity、confidence、rationale。"
            "幻觉结果的 category_names 必须且只能包含 primary_category 一个值。不要输出思维过程。"
        )

    @staticmethod
    def _build_prompt(
        user_question: str,
        system_reply: str,
        evidence: list[dict[str, object]],
        categories: list[dict[str, object]],
    ) -> str:
        data: dict[str, Any] = {
            "user_question": user_question,
            "system_reply": system_reply,
            "retrieved_evidence": evidence,
            "allowed_categories": categories,
            "severity_values": ["low", "medium", "high", "critical"],
            "output_constraints": {
                "hallucination": "category_names 只能包含 primary_category 一个允许分类",
                "normal": "category_names 为空且 primary_category 为 null",
                "category_selection": "优先最具体分类；只有具体程度相同才比较严重程度",
            },
        }
        return "请审计以下客服回复，并输出 JSON：\n" + json.dumps(data, ensure_ascii=False)
