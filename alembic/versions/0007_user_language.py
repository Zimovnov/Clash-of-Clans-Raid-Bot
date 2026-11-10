"""add user language preference

Revision ID: 0007_user_language
Revises: 0006_player_profiles
Create Date: 2026-03-22 18:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_user_language"
down_revision: Union[str, None] = "0006_player_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_language = sa.Enum("en", "ru", name="user_language")


def upgrade() -> None:
    user_language.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "language",
            user_language,
            nullable=False,
            server_default=sa.text("'en'"),
        ),
    )
    op.execute("UPDATE users SET language = 'en' WHERE language IS NULL")


def downgrade() -> None:
    op.drop_column("users", "language")
    user_language.drop(op.get_bind(), checkfirst=True)
