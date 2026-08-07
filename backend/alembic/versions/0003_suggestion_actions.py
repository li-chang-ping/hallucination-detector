"""支持新增、修改和归档分类建议。

Revision ID: 0003_suggestion_actions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_suggestion_actions"
down_revision: str | None = "0002_evaluation_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("category_suggestions") as batch_op:
        batch_op.add_column(
            sa.Column("action", sa.String(20), nullable=False, server_default="update")
        )
        batch_op.alter_column("category_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("category_suggestions") as batch_op:
        batch_op.alter_column("category_id", existing_type=sa.String(36), nullable=False)
        batch_op.drop_column("action")
