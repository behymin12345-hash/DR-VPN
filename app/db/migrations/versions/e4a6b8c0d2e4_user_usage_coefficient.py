"""per-user usage coefficient

Revision ID: e4a6b8c0d2e4
Revises: d2e4f6a8b0c1
Create Date: 2026-11-08 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e4a6b8c0d2e4'
down_revision = 'd2e4f6a8b0c1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("usage_coefficient", sa.Float(), nullable=False, server_default=sa.text("1.0"))
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("usage_coefficient")
