from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Severity


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=1000)
    default_severity: Severity
    prompt_guidance: str = Field(default="", max_length=2000)
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, min_length=2, max_length=1000)
    default_severity: Severity | None = None
    prompt_guidance: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class CategoryRead(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

