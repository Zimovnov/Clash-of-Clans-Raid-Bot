"""add newbie baseline to clans

Revision ID: 0003_newbie_baseline
Revises: 0002_access_requests
Create Date: 2026-03-22 13:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_newbie_baseline"
down_revision: Union[str, None] = "0002_access_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clans", sa.Column("newbie_baseline_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("clans", "newbie_baseline_at")
