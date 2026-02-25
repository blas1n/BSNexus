"""add worker-project assignment

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-02-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add project_id FK to workers table
    op.add_column("workers", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_workers_project_id",
        "workers",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add worker_id to design_sessions (plain UUID, no FK)
    op.add_column("design_sessions", sa.Column("worker_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("design_sessions", "worker_id")
    op.drop_constraint("fk_workers_project_id", "workers", type_="foreignkey")
    op.drop_column("workers", "project_id")
