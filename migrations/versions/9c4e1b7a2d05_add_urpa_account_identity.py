"""add urpa account identity

Revision ID: 9c4e1b7a2d05
Revises: 7b2d89e54c31
Create Date: 2026-08-28 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '9c4e1b7a2d05'
down_revision = '7b2d89e54c31'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phone', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('urpa_user_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('urpa_linked_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column(
            'account_origin', sa.String(length=24), nullable=False, server_default='email'
        ))
        batch_op.create_index('ix_users_phone', ['phone'], unique=True)
        batch_op.create_index('ix_users_urpa_user_id', ['urpa_user_id'], unique=True)
        batch_op.create_index('ix_users_account_origin', ['account_origin'], unique=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_account_origin')
        batch_op.drop_index('ix_users_urpa_user_id')
        batch_op.drop_index('ix_users_phone')
        batch_op.drop_column('account_origin')
        batch_op.drop_column('urpa_linked_at')
        batch_op.drop_column('urpa_user_id')
        batch_op.drop_column('phone')
