"""add error records table

Revision ID: c1e72f6b4a90
Revises: a8d75f2c91b4
Create Date: 2026-08-23 21:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1e72f6b4a90'
down_revision = 'a8d75f2c91b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'error_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('exception_type', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('request_method', sa.String(length=16), nullable=True),
        sa.Column('request_path', sa.Text(), nullable=True),
        sa.Column('endpoint', sa.String(length=255), nullable=True),
        sa.Column('query_params', sa.Text(), nullable=True),
        sa.Column('request_payload', sa.Text(), nullable=True),
        sa.Column('request_headers', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_email', sa.String(length=255), nullable=True),
        sa.Column('client_ip', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('environment', sa.String(length=64), nullable=True),
        sa.Column('release', sa.String(length=128), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by_id', sa.Integer(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
    )
    op.create_index(op.f('ix_error_records_fingerprint'), 'error_records', ['fingerprint'], unique=True)
    op.create_index(op.f('ix_error_records_last_seen_at'), 'error_records', ['last_seen_at'], unique=False)
    op.create_index(op.f('ix_error_records_severity'), 'error_records', ['severity'], unique=False)
    op.create_index(op.f('ix_error_records_status'), 'error_records', ['status'], unique=False)
    op.create_index(op.f('ix_error_records_user_id'), 'error_records', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_error_records_user_id'), table_name='error_records')
    op.drop_index(op.f('ix_error_records_status'), table_name='error_records')
    op.drop_index(op.f('ix_error_records_severity'), table_name='error_records')
    op.drop_index(op.f('ix_error_records_last_seen_at'), table_name='error_records')
    op.drop_index(op.f('ix_error_records_fingerprint'), table_name='error_records')
    op.drop_table('error_records')
