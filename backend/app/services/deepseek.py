import asyncio
import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
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
                            "temperature": 0.1,
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

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是严格的智能客服幻觉审计器。只能以检索证据为事实来源，不得使用常识补全。"
            "需要识别直接矛盾、无证据的肯定事实、虚假的执行能力、安全误导和实质性遗漏。"
            "输出必须是 JSON 对象，字段为 is_hallucination、category_names、"
            "primary_category、severity、confidence、rationale。不要输出思维过程。"
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
            "output_example": {
                "is_hallucination": True,
                "category_names": ["产品参数错误"],
                "primary_category": "产品参数错误",
                "severity": "high",
                "confidence": 0.95,
                "rationale": "回复中的参数与证据直接矛盾。",
            },
        }
        return "请审计以下客服回复，并输出 JSON：\n" + json.dumps(data, ensure_ascii=False)

