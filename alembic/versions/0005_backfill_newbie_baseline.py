"""backfill newbie baseline for existing clans

Revision ID: 0005_backfill_newbie_baseline
Revises: 0004_player_manager_note
Create Date: 2026-03-22 14:10:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0005_backfill_newbie_baseline"
down_revision: Union[str, None] = "0004_player_manager_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE clans SET newbie_baseline_at = now() WHERE newbie_baseline_at IS NULL")


def downgrade() -> None:
    op.execute("UPDATE clans SET newbie_baseline_at = NULL")
