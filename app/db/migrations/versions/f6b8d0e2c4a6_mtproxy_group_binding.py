"""mtproto proxy group binding

Revision ID: f6b8d0e2c4a6
Revises: e4a6b8c0d2e4
Create Date: 2026-11-10 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import SqliteCompatibleBigInteger

# revision identifiers, used by Alembic.
revision = 'f6b8d0e2c4a6'
down_revision = 'e4a6b8c0d2e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mtproto_proxies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "group_id",
                SqliteCompatibleBigInteger(),
                sa.ForeignKey("groups.id", ondelete="CASCADE", name="fk_mtproto_proxies_group_id_groups"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("mtproto_proxies", schema=None) as batch_op:
        batch_op.drop_column("group_id")
