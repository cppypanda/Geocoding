"""add payment provider fields

Revision ID: a8d75f2c91b4
Revises: 039df70ac954
Create Date: 2026-08-23 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a8d75f2c91b4'
down_revision = '039df70ac954'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recharge_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('provider_trade_no', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('buyer_logon_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('notify_payload', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('paid_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('recharge_orders', schema=None) as batch_op:
        batch_op.drop_column('paid_at')
        batch_op.drop_column('notify_payload')
        batch_op.drop_column('buyer_logon_id')
        batch_op.drop_column('provider_trade_no')
        batch_op.drop_column('payment_url')
