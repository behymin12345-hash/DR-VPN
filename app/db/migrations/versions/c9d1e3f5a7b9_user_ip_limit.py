"""user ip_limit

Revision ID: c9d1e3f5a7b9
Revises: f6b8d0e2c4a6
Create Date: 2026-11-15 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import SqliteCompatibleBigInteger

# revision identifiers, used by Alembic.
revision = 'c9d1e3f5a7b9'
down_revision = 'f6b8d0e2c4a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ip_limit", SqliteCompatibleBigInteger(), nullable=True))
    with op.batch_alter_table("user_templates", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ip_limit", SqliteCompatibleBigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_templates", schema=None) as batch_op:
        batch_op.drop_column("ip_limit")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("ip_limit")
