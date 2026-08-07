from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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

