"""add email verification codes

Revision ID: d42a9c81ef07
Revises: c1e72f6b4a90
Create Date: 2026-08-23 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd42a9c81ef07'
down_revision = 'c1e72f6b4a90'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_verification_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('purpose', sa.String(length=40), nullable=False),
        sa.Column('code_digest', sa.String(length=64), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', 'purpose', name='uq_verification_email_purpose'),
    )
    op.create_index(
        'ix_verification_email_purpose',
        'email_verification_codes',
        ['email', 'purpose'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_verification_email_purpose', table_name='email_verification_codes')
    op.drop_table('email_verification_codes')
