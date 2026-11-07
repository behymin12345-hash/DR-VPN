"""mtproto proxies table

Revision ID: b5c7d9e1f3a5
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.db.models import SqliteCompatibleBigInteger


# revision identifiers, used by Alembic.
revision = 'b5c7d9e1f3a5'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mtproto_proxies",
        sa.Column("id", SqliteCompatibleBigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("server", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("secret", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("mtproto_proxies")
