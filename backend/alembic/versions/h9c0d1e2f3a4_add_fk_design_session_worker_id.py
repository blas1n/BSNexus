"""add FK constraint on design_sessions.worker_id

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
Create Date: 2026-02-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h9c0d1e2f3a4"
down_revision: Union[str, None] = "g8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_design_sessions_worker_id",
        "design_sessions",
        "workers",
        ["worker_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_design_sessions_worker_id", "design_sessions", type_="foreignkey")
