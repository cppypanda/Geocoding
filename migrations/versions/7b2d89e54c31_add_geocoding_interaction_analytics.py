"""add geocoding interaction analytics

Revision ID: 7b2d89e54c31
Revises: f64c1be80329
Create Date: 2026-08-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '7b2d89e54c31'
down_revision = 'f64c1be80329'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('geocoding_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('run_mode', sa.String(length=32), nullable=False, server_default='multisource'))
        batch_op.add_column(sa.Column('trigger_origin', sa.String(length=64), nullable=False, server_default='unknown'))
        batch_op.add_column(sa.Column('client_session_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('client_action_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('semantic_web_search_performed', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('semantic_web_search_success', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index('ix_geocoding_tasks_run_mode', ['run_mode'], unique=False)
        batch_op.create_index('ix_geocoding_tasks_trigger_origin', ['trigger_origin'], unique=False)
        batch_op.create_index('ix_geocoding_tasks_client_session_id', ['client_session_id'], unique=False)
        batch_op.create_index('ix_geocoding_tasks_client_action_id', ['client_action_id'], unique=False)

    with op.batch_alter_table('address_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address_index', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('initial_source', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('initial_latitude_wgs84', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('initial_longitude_wgs84', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('final_source', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('final_confidence', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('final_latitude_wgs84', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('final_longitude_wgs84', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('selection_method', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('correction_source', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('corrected', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('web_search_used', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_address_logs_initial_source', ['initial_source'], unique=False)
        batch_op.create_index('ix_address_logs_final_source', ['final_source'], unique=False)
        batch_op.create_index('ix_address_logs_selection_method', ['selection_method'], unique=False)
        batch_op.create_index('ix_address_logs_correction_source', ['correction_source'], unique=False)
        batch_op.create_index('ix_address_logs_corrected', ['corrected'], unique=False)
        batch_op.create_index('ix_address_logs_web_search_used', ['web_search_used'], unique=False)

    op.create_table(
        'interaction_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('geocoding_task_id', sa.Integer(), nullable=True),
        sa.Column('address_log_id', sa.Integer(), nullable=True),
        sa.Column('client_event_id', sa.String(length=64), nullable=True),
        sa.Column('client_action_id', sa.String(length=64), nullable=True),
        sa.Column('client_session_id', sa.String(length=64), nullable=True),
        sa.Column('event_name', sa.String(length=80), nullable=False),
        sa.Column('event_source', sa.String(length=16), nullable=False),
        sa.Column('trigger_origin', sa.String(length=64), nullable=False),
        sa.Column('button_id', sa.String(length=80), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['address_log_id'], ['address_logs.id']),
        sa.ForeignKeyConstraint(['geocoding_task_id'], ['geocoding_tasks.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in (
        'user_id', 'geocoding_task_id', 'address_log_id', 'client_event_id',
        'client_action_id', 'client_session_id', 'event_name', 'event_source',
        'trigger_origin', 'button_id', 'created_at',
    ):
        op.create_index(
            f'ix_interaction_events_{column}',
            'interaction_events',
            [column],
            unique=(column == 'client_event_id'),
        )

    op.create_table(
        'point_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('geocoding_task_id', sa.Integer(), nullable=True),
        sa.Column('transaction_type', sa.String(length=16), nullable=False),
        sa.Column('task_key', sa.String(length=64), nullable=False),
        sa.Column('points_delta', sa.Integer(), nullable=False),
        sa.Column('balance_after', sa.Integer(), nullable=False),
        sa.Column('operation_id', sa.String(length=128), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['geocoding_task_id'], ['geocoding_tasks.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in (
        'user_id', 'geocoding_task_id', 'transaction_type', 'task_key',
        'operation_id', 'idempotency_key', 'created_at',
    ):
        op.create_index(
            f'ix_point_transactions_{column}',
            'point_transactions',
            [column],
            unique=(column == 'idempotency_key'),
        )


def downgrade():
    op.drop_table('point_transactions')
    op.drop_table('interaction_events')
    with op.batch_alter_table('address_logs', schema=None) as batch_op:
        for name in (
            'ix_address_logs_web_search_used', 'ix_address_logs_corrected',
            'ix_address_logs_correction_source', 'ix_address_logs_selection_method',
            'ix_address_logs_final_source', 'ix_address_logs_initial_source',
        ):
            batch_op.drop_index(name)
        for column in (
            'updated_at', 'web_search_used', 'corrected', 'correction_source',
            'selection_method', 'final_longitude_wgs84', 'final_latitude_wgs84',
            'final_confidence', 'final_source', 'initial_longitude_wgs84',
            'initial_latitude_wgs84', 'initial_source', 'address_index',
        ):
            batch_op.drop_column(column)
    with op.batch_alter_table('geocoding_tasks', schema=None) as batch_op:
        batch_op.drop_index('ix_geocoding_tasks_client_action_id')
        batch_op.drop_index('ix_geocoding_tasks_client_session_id')
        batch_op.drop_index('ix_geocoding_tasks_trigger_origin')
        batch_op.drop_index('ix_geocoding_tasks_run_mode')
        for column in (
            'semantic_web_search_success', 'semantic_web_search_performed',
            'client_action_id', 'client_session_id', 'trigger_origin', 'run_mode',
        ):
            batch_op.drop_column(column)
