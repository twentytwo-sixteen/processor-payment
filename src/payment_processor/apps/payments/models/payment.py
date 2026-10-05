from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import payment_processor.constants.errors
import payment_processor.constants.payments
from payment_processor.apps.core.database.base import Base
from payment_processor.apps.core.types import JsonObject


class Payment(Base):
    __tablename__ = 'payments'
    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_payment_positive_amount'),
        CheckConstraint("currency IN ('RUB', 'USD', 'EUR')", name='ck_payment_currency'),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name='ck_payment_status'),
        CheckConstraint("status = 'pending' OR processed_at IS NOT NULL", name='ck_payment_terminal_date'),
        CheckConstraint('processing_attempt BETWEEN 1 AND 3', name='ck_payment_processing_attempt'),
        CheckConstraint('webhook_attempts BETWEEN 0 AND 3', name='ck_payment_webhook_attempts'),
        CheckConstraint(
            "webhook_status IN ('not_ready', 'pending', 'delivered', 'exhausted')",
            name='ck_payment_webhook_status',
        ),
        Index('ix_payment_active_lease', 'lease_expires_at', postgresql_where=text('lease_token IS NOT NULL')),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(
            payment_processor.constants.payments.PAYMENT_AMOUNT_MAX_DIGITS,
            payment_processor.constants.payments.PAYMENT_AMOUNT_DECIMAL_PLACES,
        ),
    )
    currency: Mapped[str] = mapped_column(String(payment_processor.constants.payments.PAYMENT_CURRENCY_MAX_LENGTH))
    description: Mapped[str] = mapped_column(
        String(payment_processor.constants.payments.PAYMENT_DESCRIPTION_MAX_LENGTH),
    )
    metadata_json: Mapped[JsonObject] = mapped_column('metadata', JSONB)
    status: Mapped[str] = mapped_column(String(payment_processor.constants.payments.PAYMENT_STATUS_MAX_LENGTH))
    idempotency_key: Mapped[str] = mapped_column(
        String(payment_processor.constants.payments.PAYMENT_IDEMPOTENCY_KEY_MAX_LENGTH),
        unique=True,
    )
    request_hash: Mapped[str] = mapped_column(String(payment_processor.constants.payments.PAYMENT_REQUEST_HASH_LENGTH))
    webhook_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gateway_reference: Mapped[str | None] = mapped_column(
        String(payment_processor.constants.payments.PAYMENT_GATEWAY_REFERENCE_MAX_LENGTH),
    )
    failure_code: Mapped[str | None] = mapped_column(String(payment_processor.constants.errors.ERROR_CODE_MAX_LENGTH))
    webhook_event_id: Mapped[UUID | None]
    webhook_payload: Mapped[JsonObject | None] = mapped_column(JSONB)
    webhook_status: Mapped[str] = mapped_column(
        String(payment_processor.constants.payments.PAYMENT_STATUS_MAX_LENGTH),
        server_default=payment_processor.constants.payments.WebhookStatus.NOT_READY.value,
    )
    webhook_attempts: Mapped[int] = mapped_column(Integer, server_default='0')
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    webhook_last_error: Mapped[str | None] = mapped_column(
        String(payment_processor.constants.errors.ERROR_CODE_MAX_LENGTH)
    )
    processing_attempt: Mapped[int] = mapped_column(
        Integer,
        server_default=str(payment_processor.constants.payments.PAYMENT_PROCESSING_ATTEMPT_INITIAL),
    )
    expected_event_id: Mapped[UUID]
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
