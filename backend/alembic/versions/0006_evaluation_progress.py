"""记录评测后台处理进度和事件。

Revision ID: 0006_evaluation_progress
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_evaluation_progress"
down_revision: str | None = "0005_evaluation_insight_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.add_column(
            sa.Column("insight_progress", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("insight_stage", sa.String(200), nullable=False, server_default="等待分析")
        )
        batch_op.add_column(
            sa.Column("insight_events", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("ground_truth_snapshot", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.drop_column("ground_truth_snapshot")
        batch_op.drop_column("insight_events")
        batch_op.drop_column("insight_stage")
        batch_op.drop_column("insight_progress")
