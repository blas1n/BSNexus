"""add message_type to design_messages

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-02-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    message_type_enum = sa.Enum("chat", "internal", name="messagetype")
    message_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "design_messages",
        sa.Column("message_type", message_type_enum, nullable=False, server_default="chat"),
    )


def downgrade() -> None:
    op.drop_column("design_messages", "message_type")
    sa.Enum(name="messagetype").drop(op.get_bind(), checkfirst=True)
