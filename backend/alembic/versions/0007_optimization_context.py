"""保存跨轮优化上下文和建议影响分析。

Revision ID: 0007_optimization_context
Revises: 0006_evaluation_progress
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_optimization_context"
down_revision: str | None = "0006_evaluation_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.add_column(
            sa.Column("optimization_context", sa.JSON(), nullable=False, server_default="{}")
        )
    with op.batch_alter_table("category_suggestions") as batch_op:
        batch_op.add_column(
            sa.Column("impact_analysis", sa.JSON(), nullable=False, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("category_suggestions") as batch_op:
        batch_op.drop_column("impact_analysis")
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.drop_column("optimization_context")
