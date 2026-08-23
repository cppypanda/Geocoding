"""add soft delete to users

Revision ID: f64c1be80329
Revises: e53b0ad79218
Create Date: 2026-08-23 21:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f64c1be80329'
down_revision = 'e53b0ad79218'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('is_deleted')
