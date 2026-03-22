"""add clan access requests

Revision ID: 0002_access_requests
Revises: 0001_init
Create Date: 2026-03-22 00:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0002_access_requests"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


clan_role = postgresql.ENUM("owner", "manager", name="clan_role", create_type=False)
clan_access_request_status = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    name="clan_access_request_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    clan_access_request_status.create(bind, checkfirst=True)

    op.create_table(
        "clan_access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clan_id", sa.Integer(), sa.ForeignKey("clans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_role", clan_role, nullable=False, server_default=sa.text("'manager'")),
        sa.Column("status", clan_access_request_status, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_clan_access_requests_clan_id", "clan_access_requests", ["clan_id"])
    op.create_index("ix_clan_access_requests_user_id", "clan_access_requests", ["user_id"])
    op.create_index("ix_clan_access_requests_status", "clan_access_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_clan_access_requests_status", table_name="clan_access_requests")
    op.drop_index("ix_clan_access_requests_user_id", table_name="clan_access_requests")
    op.drop_index("ix_clan_access_requests_clan_id", table_name="clan_access_requests")
    op.drop_table("clan_access_requests")

    bind = op.get_bind()
    clan_access_request_status.drop(bind, checkfirst=True)
