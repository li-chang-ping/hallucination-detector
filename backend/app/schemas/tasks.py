from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import Severity, TaskStatus


class ReplyInput(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    user_question: str = Field(min_length=1, max_length=10000)
    system_reply: str = Field(min_length=1, max_length=30000)

    model_config = ConfigDict(extra="ignore")


class ReplyBatch(BaseModel):
    items: list[ReplyInput]

    @model_validator(mode="after")
    def validate_items(self) -> "ReplyBatch":
        if not 1 <= len(self.items) <= 10000:
            raise ValueError("每个任务必须包含 1 到 10000 条回复")
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("回复 id 必须唯一")
        return self


class DetectionDecision(BaseModel):
    is_hallucination: bool
    category_names: list[str] = Field(default_factory=list)
    primary_category: str | None = None
    severity: Severity | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def consistent_result(self) -> "DetectionDecision":
        if self.is_hallucination:
            if len(self.category_names) != 1 or self.primary_category != self.category_names[0]:
                raise ValueError("幻觉结果必须且只能包含一个分类，并与主分类一致")
            if self.severity is None:
                raise ValueError("幻觉结果必须包含严重度")
        else:
            self.category_names = []
            self.primary_category = None
            self.severity = None
        return self


class DetectionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    input_id: str
    position: int
    user_question: str
    system_reply: str
    status: str
    evidence_snapshot: list[dict[str, object]]
    error_message: str | None
    is_hallucination: bool | None
    category_names: list[str]
    primary_category: str | None
    severity: str | None
    confidence: float | None
    rationale: str | None
    prompt_tokens: int
    completion_tokens: int


class DetectionTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    knowledge_base_id: str | None
    status: TaskStatus
    model_name: str
    total_count: int
    completed_count: int
    error_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DetectionTaskDetail(DetectionTaskRead):
    category_snapshot: list[dict[str, object]]
    items: list[DetectionItemRead]
