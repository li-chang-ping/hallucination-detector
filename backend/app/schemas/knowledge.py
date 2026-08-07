from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)


class KnowledgeEntryCreate(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeEntryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    metadata: dict[str, object] | None = None


class KnowledgeImport(KnowledgeBaseCreate):
    entries: list[KnowledgeEntryCreate] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_ids(self) -> "KnowledgeImport":
        ids = [item.id for item in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("知识条目 id 必须唯一")
        return self


class KnowledgeBaseRead(KnowledgeBaseCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    embedding_model: str
    created_at: datetime
    updated_at: datetime
    entry_count: int = 0


class KnowledgeEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    knowledge_base_id: str
    title: str
    content: str
    extra_metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime

