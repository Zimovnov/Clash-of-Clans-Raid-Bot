"""create mvp schema

Revision ID: 0001_init
Revises:
Create Date: 2026-03-22 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


clan_role = postgresql.ENUM("owner", "manager", name="clan_role", create_type=False)
report_category = postgresql.ENUM("kick", "questionable", "newbie", "left_clan", "ok", name="report_category", create_type=False)
report_source = postgresql.ENUM("auto", "manual", "retry", name="report_source", create_type=False)
report_status = postgresql.ENUM("success", "failed", name="report_status", create_type=False)
job_status = postgresql.ENUM("running", "success", "failed", name="job_status", create_type=False)
outbox_status = postgresql.ENUM("pending", "sent", "failed", name="outbox_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    clan_role.create(bind, checkfirst=True)
    report_category.create(bind, checkfirst=True)
    report_source.create(bind, checkfirst=True)
    report_status.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)
    outbox_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "clans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_tracking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_clans_tag", "clans", ["tag"], unique=True)

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_players_tag", "players", ["tag"], unique=True)

    op.create_table(
        "clan_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", clan_role, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("clan_id", "user_id", name="uq_clan_access_clan_user"),
    )
    op.create_index("ix_clan_access_clan_id", "clan_access", ["clan_id"])
    op.create_index("ix_clan_access_user_id", "clan_access", ["user_id"])
    op.create_index("ix_clan_access_role", "clan_access", ["role"])

    op.create_table(
        "player_clan_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_seen_in_clan_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_in_clan_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_current_member", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("player_id", "clan_id", name="uq_player_clan_state_player_clan"),
    )
    op.create_index("ix_player_clan_state_player_id", "player_clan_state", ["player_id"])
    op.create_index("ix_player_clan_state_clan_id", "player_clan_state", ["clan_id"])
    op.create_index("ix_player_clan_state_is_current_member", "player_clan_state", ["is_current_member"])

    op.create_table(
        "clan_membership_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("member_tags", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_clan_membership_snapshots_clan_id", "clan_membership_snapshots", ["clan_id"])
    op.create_index("ix_clan_membership_snapshots_taken_at", "clan_membership_snapshots", ["taken_at"])

    op.create_table(
        "raid_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raid_weekend_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raid_weekend_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", report_source, nullable=False),
        sa.Column("status", report_status, nullable=False, server_default=sa.text("'success'")),
        sa.Column("kick_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("newbie_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("left_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ok_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_raid_reports_clan_id", "raid_reports", ["clan_id"])
    op.create_index("ix_raid_reports_generated_at", "raid_reports", ["generated_at"])
    op.create_index("ix_raid_reports_source", "raid_reports", ["source"])

    op.create_table(
        "raid_report_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("raid_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True),
        sa.Column("player_tag", sa.String(length=32), nullable=False),
        sa.Column("player_name", sa.String(length=255), nullable=False),
        sa.Column("attacks_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("category", report_category, nullable=False),
        sa.Column("is_current_member", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("first_seen_in_clan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_clan_note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_raid_report_players_report_id", "raid_report_players", ["report_id"])
    op.create_index("ix_raid_report_players_player_tag", "raid_report_players", ["player_tag"])
    op.create_index("ix_raid_report_players_category", "raid_report_players", ["category"])

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(length=255), nullable=False),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", job_status, nullable=False, server_default=sa.text("'running'")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_job_runs_job_name", "job_runs", ["job_name"])
    op.create_index("ix_job_runs_clan_id", "job_runs", ["clan_id"])

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("raid_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_type", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("status", outbox_status, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outbox_messages_clan_id", "outbox_messages", ["clan_id"])
    op.create_index("ix_outbox_messages_user_id", "outbox_messages", ["user_id"])
    op.create_index("ix_outbox_messages_message_type", "outbox_messages", ["message_type"])
    op.create_index("ix_outbox_messages_dedupe_key", "outbox_messages", ["dedupe_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_dedupe_key", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_message_type", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_user_id", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_clan_id", table_name="outbox_messages")
    op.drop_table("outbox_messages")

    op.drop_index("ix_job_runs_clan_id", table_name="job_runs")
    op.drop_index("ix_job_runs_job_name", table_name="job_runs")
    op.drop_table("job_runs")

    op.drop_index("ix_raid_report_players_category", table_name="raid_report_players")
    op.drop_index("ix_raid_report_players_player_tag", table_name="raid_report_players")
    op.drop_index("ix_raid_report_players_report_id", table_name="raid_report_players")
    op.drop_table("raid_report_players")

    op.drop_index("ix_raid_reports_source", table_name="raid_reports")
    op.drop_index("ix_raid_reports_generated_at", table_name="raid_reports")
    op.drop_index("ix_raid_reports_clan_id", table_name="raid_reports")
    op.drop_table("raid_reports")

    op.drop_index("ix_clan_membership_snapshots_taken_at", table_name="clan_membership_snapshots")
    op.drop_index("ix_clan_membership_snapshots_clan_id", table_name="clan_membership_snapshots")
    op.drop_table("clan_membership_snapshots")

    op.drop_index("ix_player_clan_state_is_current_member", table_name="player_clan_state")
    op.drop_index("ix_player_clan_state_clan_id", table_name="player_clan_state")
    op.drop_index("ix_player_clan_state_player_id", table_name="player_clan_state")
    op.drop_table("player_clan_state")

    op.drop_index("ix_clan_access_role", table_name="clan_access")
    op.drop_index("ix_clan_access_user_id", table_name="clan_access")
    op.drop_index("ix_clan_access_clan_id", table_name="clan_access")
    op.drop_table("clan_access")

    op.drop_index("ix_players_tag", table_name="players")
    op.drop_table("players")

    op.drop_index("ix_clans_tag", table_name="clans")
    op.drop_table("clans")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    outbox_status.drop(bind, checkfirst=True)
    job_status.drop(bind, checkfirst=True)
    report_status.drop(bind, checkfirst=True)
    report_source.drop(bind, checkfirst=True)
    report_category.drop(bind, checkfirst=True)
    clan_role.drop(bind, checkfirst=True)
