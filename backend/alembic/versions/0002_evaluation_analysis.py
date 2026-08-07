"""增加误判分析、优化建议与分类版本。

Revision ID: 0002_evaluation_analysis
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_evaluation_analysis"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "category_id",
            sa.String(36),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_category_versions_category_id", "category_versions", ["category_id"])
    op.create_table(
        "evaluation_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.String(36),
            sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_id", sa.String(120), nullable=False),
        sa.Column("error_type", sa.String(20), nullable=False),
        sa.Column("human_category", sa.String(80), nullable=True),
        sa.Column("predicted_category", sa.String(80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("likely_cause", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_evaluation_analyses_evaluation_id", "evaluation_analyses", ["evaluation_id"]
    )
    op.create_index("ix_evaluation_analyses_input_id", "evaluation_analyses", ["input_id"])
    op.create_table(
        "category_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.String(36),
            sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("target_category_name", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_category_suggestions_evaluation_id", "category_suggestions", ["evaluation_id"]
    )
    op.create_index("ix_category_suggestions_category_id", "category_suggestions", ["category_id"])


def downgrade() -> None:
    op.drop_table("category_suggestions")
    op.drop_table("evaluation_analyses")
    op.drop_table("category_versions")
