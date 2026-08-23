"""unique user api key service

Revision ID: e53b0ad79218
Revises: d42a9c81ef07
Create Date: 2026-08-23 21:40:00.000000
"""

from alembic import op


revision = 'e53b0ad79218'
down_revision = 'd42a9c81ef07'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        'DELETE FROM user_api_keys WHERE id NOT IN '
        '(SELECT MIN(id) FROM user_api_keys GROUP BY user_id, service_name)'
    )
    with op.batch_alter_table('user_api_keys', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_user_api_key_service', ['user_id', 'service_name'])


def downgrade():
    with op.batch_alter_table('user_api_keys', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_api_key_service', type_='unique')
