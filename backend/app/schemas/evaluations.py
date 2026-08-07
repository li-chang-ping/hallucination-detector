from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

REMOVED_METRICS = {"f1", "category_accuracy", "category_stats"}


class GroundTruthItem(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    is_hallucination: bool
    hallucination_type: str | None = None
    detail: str = ""


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    metrics: dict[str, object]
    ground_truth_count: int
    created_at: datetime

    @field_validator("metrics")
    @classmethod
    def remove_unsupported_metrics(cls, value: dict[str, object]) -> dict[str, object]:
        """隐藏旧评测快照中当前题目不要求的指标。"""
        return {name: metric for name, metric in value.items() if name not in REMOVED_METRICS}

