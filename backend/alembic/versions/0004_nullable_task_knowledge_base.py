"""允许已完成任务在知识库删除后保留。

Revision ID: 0004_nullable_task_knowledge_base
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_nullable_task_knowledge_base"
down_revision: str | None = "0003_suggestion_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    naming_convention = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table("detection_tasks", naming_convention=naming_convention) as batch_op:
        batch_op.drop_constraint(
            "fk_detection_tasks_knowledge_base_id_knowledge_bases", type_="foreignkey"
        )
        batch_op.alter_column("knowledge_base_id", existing_type=sa.String(36), nullable=True)
        batch_op.create_foreign_key(
            "fk_detection_tasks_knowledge_base_id",
            "knowledge_bases",
            ["knowledge_base_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("detection_tasks") as batch_op:
        batch_op.drop_constraint("fk_detection_tasks_knowledge_base_id", type_="foreignkey")
        batch_op.alter_column("knowledge_base_id", existing_type=sa.String(36), nullable=False)
        batch_op.create_foreign_key(
            "fk_detection_tasks_knowledge_base_id",
            "knowledge_bases",
            ["knowledge_base_id"],
            ["id"],
        )
