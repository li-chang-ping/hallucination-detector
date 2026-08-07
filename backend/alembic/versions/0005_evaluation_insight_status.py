"""记录评测分析状态与失败原因。

Revision ID: 0005_evaluation_insight_status
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_evaluation_insight_status"
down_revision: str | None = "0004_nullable_task_knowledge_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "insight_status",
                sa.String(20),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(sa.Column("insight_error", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.drop_column("insight_error")
        batch_op.drop_column("insight_status")
