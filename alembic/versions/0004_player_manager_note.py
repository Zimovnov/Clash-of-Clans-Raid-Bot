"""add manager note to player clan state

Revision ID: 0004_player_manager_note
Revises: 0003_newbie_baseline
Create Date: 2026-03-22 13:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_player_manager_note"
down_revision: Union[str, None] = "0003_newbie_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_clan_state", sa.Column("manager_note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("player_clan_state", "manager_note")
