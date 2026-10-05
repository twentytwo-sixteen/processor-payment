from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'payments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('webhook_url', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('gateway_reference', sa.String(length=128), nullable=True),
        sa.Column('failure_code', sa.String(length=64), nullable=True),
        sa.Column('webhook_event_id', sa.Uuid(), nullable=True),
        sa.Column('webhook_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('webhook_status', sa.String(length=16), server_default='not_ready', nullable=False),
        sa.Column('webhook_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('webhook_delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('webhook_last_error', sa.String(length=64), nullable=True),
        sa.Column('processing_attempt', sa.Integer(), server_default='1', nullable=False),
        sa.Column('expected_event_id', sa.Uuid(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lease_token', sa.Uuid(), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_exhausted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("currency IN ('RUB', 'USD', 'EUR')", name='ck_payment_currency'),
        sa.CheckConstraint("status = 'pending' OR processed_at IS NOT NULL", name='ck_payment_terminal_date'),
        sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name='ck_payment_status'),
        sa.CheckConstraint(
            "webhook_status IN ('not_ready', 'pending', 'delivered', 'exhausted')", name='ck_payment_webhook_status'
        ),
        sa.CheckConstraint('amount > 0', name='ck_payment_positive_amount'),
        sa.CheckConstraint('processing_attempt BETWEEN 1 AND 3', name='ck_payment_processing_attempt'),
        sa.CheckConstraint('webhook_attempts BETWEEN 0 AND 3', name='ck_payment_webhook_attempts'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index(
        'ix_payment_active_lease',
        'payments',
        ['lease_expires_at'],
        unique=False,
        postgresql_where=sa.text('lease_token IS NOT NULL'),
    )
    op.create_table(
        'outbox',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('payment_id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('schema_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('exchange', sa.String(length=64), nullable=False),
        sa.Column('routing_key', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('publish_attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.String(length=64), nullable=True),
        sa.Column('lease_token', sa.Uuid(), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('attempt BETWEEN 1 AND 3', name='ck_outbox_attempt'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_id', 'event_type', 'attempt', name='uq_outbox_logical_attempt'),
    )
    op.create_index(
        'ix_outbox_ready',
        'outbox',
        ['available_at', 'id'],
        unique=False,
        postgresql_where=sa.text('published_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_outbox_ready', table_name='outbox', postgresql_where=sa.text('published_at IS NULL'))
    op.drop_table('outbox')
    op.drop_index('ix_payment_active_lease', table_name='payments', postgresql_where=sa.text('lease_token IS NOT NULL'))
    op.drop_table('payments')
