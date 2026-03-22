"""add player profiles

Revision ID: 0006_player_profiles
Revises: 0005_backfill_newbie_baseline
Create Date: 2026-03-22 14:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_player_profiles"
down_revision: Union[str, None] = "0005_backfill_newbie_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exp_level", sa.Integer(), nullable=True),
        sa.Column("town_hall_level", sa.Integer(), nullable=True),
        sa.Column("builder_hall_level", sa.Integer(), nullable=True),
        sa.Column("league_name", sa.String(length=255), nullable=True),
        sa.Column("clan_role", sa.String(length=64), nullable=True),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("player_id", name="uq_player_profiles_player"),
    )
    op.create_index("ix_player_profiles_player_id", "player_profiles", ["player_id"])
    op.create_index("ix_player_profiles_refreshed_at", "player_profiles", ["refreshed_at"])


def downgrade() -> None:
    op.drop_index("ix_player_profiles_refreshed_at", table_name="player_profiles")
    op.drop_index("ix_player_profiles_player_id", table_name="player_profiles")
    op.drop_table("player_profiles")
