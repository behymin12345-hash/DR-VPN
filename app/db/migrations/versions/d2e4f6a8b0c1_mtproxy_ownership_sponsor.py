"""mtproto proxy ownership, node association and sponsored channel

Revision ID: d2e4f6a8b0c1
Revises: b5c7d9e1f3a5
Create Date: 2026-11-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e4f6a8b0c1'
down_revision = 'b5c7d9e1f3a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mtproto_proxies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("admin_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("node_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sponsored_channel", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("tag", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_mtproto_proxies_admin_id_admins", "mtproto_proxies", ["admin_id"], ["admins.id"], ondelete="CASCADE"
        )
        batch_op.create_foreign_key(
            "fk_mtproto_proxies_node_id_nodes", "mtproto_proxies", ["node_id"], ["nodes.id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("mtproto_proxies", schema=None) as batch_op:
        batch_op.drop_column("tag")
        batch_op.drop_column("sponsored_channel")
        batch_op.drop_column("node_id")
        batch_op.drop_column("admin_id")
