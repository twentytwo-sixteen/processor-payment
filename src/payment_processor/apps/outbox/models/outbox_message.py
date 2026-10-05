from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

import payment_processor.constants.errors
import payment_processor.constants.outbox
from payment_processor.apps.core.database.base import Base
from payment_processor.apps.core.types import JsonObject


class OutboxMessage(Base):
    __tablename__ = 'outbox'
    __table_args__ = (
        UniqueConstraint('payment_id', 'event_type', 'attempt', name='uq_outbox_logical_attempt'),
        CheckConstraint('attempt BETWEEN 1 AND 3', name='ck_outbox_attempt'),
        Index('ix_outbox_ready', 'available_at', 'id', postgresql_where=text('published_at IS NULL')),
    )

    payment_id: Mapped[UUID] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'))
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(payment_processor.constants.outbox.OUTBOX_EVENT_TYPE_MAX_LENGTH))
    schema_version: Mapped[int] = mapped_column(Integer, server_default='1')
    attempt: Mapped[int] = mapped_column(Integer)
    exchange: Mapped[str] = mapped_column(String(payment_processor.constants.outbox.OUTBOX_EXCHANGE_MAX_LENGTH))
    routing_key: Mapped[str] = mapped_column(String(payment_processor.constants.outbox.OUTBOX_ROUTING_KEY_MAX_LENGTH))
    payload: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(Integer, server_default='0')
    last_error: Mapped[str | None] = mapped_column(String(payment_processor.constants.errors.ERROR_CODE_MAX_LENGTH))
    lease_token: Mapped[UUID | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
