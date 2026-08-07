from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(StrEnum):
    PREPARING = "preparing"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    default_severity: Mapped[str] = mapped_column(String(16))
    prompt_guidance: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    versions: Mapped[list["CategoryVersion"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="CategoryVersion.created_at",
    )


class CategoryVersion(Base):
    __tablename__ = "category_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    category: Mapped[Category] = relationship(back_populates="versions")


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    entries: Mapped[list["KnowledgeEntry"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    external_id: Mapped[str] = mapped_column(String(120), index=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text)
    extra_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="entries")


class DetectionTask(Base):
    __tablename__ = "detection_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), index=True)
    knowledge_base_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.QUEUED)
    model_name: Mapped[str] = mapped_column(String(120))
    total_count: Mapped[int] = mapped_column(default=0)
    completed_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    category_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items: Mapped[list["DetectionItem"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="DetectionItem.position"
    )


class DetectionItem(Base):
    __tablename__ = "detection_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("detection_tasks.id", ondelete="CASCADE"), index=True
    )
    input_id: Mapped[str] = mapped_column(String(120), index=True)
    position: Mapped[int]
    user_question: Mapped[str] = mapped_column(Text)
    system_reply: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hallucination: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    category_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    primary_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    task: Mapped[DetectionTask] = relationship(back_populates="items")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("detection_tasks.id", ondelete="CASCADE"), index=True
    )
    metrics: Mapped[dict[str, object]] = mapped_column(JSON)
    ground_truth_count: Mapped[int]
    insight_status: Mapped[str] = mapped_column(String(20), default="pending")
    insight_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    analyses: Mapped[list["EvaluationAnalysis"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list["CategorySuggestion"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationAnalysis(Base):
    __tablename__ = "evaluation_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    input_id: Mapped[str] = mapped_column(String(120), index=True)
    error_type: Mapped[str] = mapped_column(String(20))
    human_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    predicted_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    likely_cause: Mapped[str] = mapped_column(Text)
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    evaluation: Mapped[Evaluation] = relationship(back_populates="analyses")


class CategorySuggestion(Base):
    __tablename__ = "category_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), default="update")
    target_category_name: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    proposed_changes: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluation: Mapped[Evaluation] = relationship(back_populates="suggestions")
