from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Severity

REMOVED_METRICS = {"f1", "category_accuracy", "category_stats"}


class GroundTruthItem(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    is_hallucination: bool
    hallucination_type: str | None = None
    detail: str = ""


class EvaluationAnalysisDraft(BaseModel):
    input_id: str = Field(min_length=1, max_length=120)
    error_type: Literal["false_negative", "false_positive"]
    reason: str = Field(min_length=2, max_length=1000)
    likely_cause: str = Field(min_length=2, max_length=1000)
    evidence_summary: str = Field(default="", max_length=1000)


class CategorySuggestionDraft(BaseModel):
    target_category_name: str = Field(min_length=2, max_length=80)
    reason: str = Field(min_length=2, max_length=1000)
    proposed_description: str | None = Field(default=None, min_length=2, max_length=1000)
    proposed_prompt_guidance: str | None = Field(default=None, min_length=2, max_length=2000)
    proposed_default_severity: Severity | None = None

    @model_validator(mode="after")
    def require_change(self) -> "CategorySuggestionDraft":
        if not any(
            (
                self.proposed_description,
                self.proposed_prompt_guidance,
                self.proposed_default_severity,
            )
        ):
            raise ValueError("优化建议至少需要修改一个字段")
        return self


class EvaluationAnalysisResponse(BaseModel):
    analyses: list[EvaluationAnalysisDraft]
    suggestions: list[CategorySuggestionDraft] = Field(default_factory=list)


class EvaluationAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    input_id: str
    error_type: str
    human_category: str | None
    predicted_category: str | None
    reason: str
    likely_cause: str
    evidence_summary: str


class CategorySuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category_id: str
    target_category_name: str
    reason: str
    proposed_changes: dict[str, object]
    status: str
    created_at: datetime
    decided_at: datetime | None


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    metrics: dict[str, object]
    ground_truth_count: int
    created_at: datetime
    analyses: list[EvaluationAnalysisRead] = Field(default_factory=list)
    suggestions: list[CategorySuggestionRead] = Field(default_factory=list)

    @field_validator("metrics")
    @classmethod
    def remove_unsupported_metrics(cls, value: dict[str, object]) -> dict[str, object]:
        """隐藏旧评测快照中当前题目不要求的指标。"""
        return {name: metric for name, metric in value.items() if name not in REMOVED_METRICS}
