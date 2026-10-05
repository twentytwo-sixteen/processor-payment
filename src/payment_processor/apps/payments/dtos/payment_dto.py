from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import payment_processor.constants.payments
from payment_processor.apps.core.types import JsonObject


@dataclass(frozen=True, slots=True)
class CreatePaymentDTO:
    amount: Decimal
    currency: payment_processor.constants.payments.Currency
    description: str
    metadata: JsonObject
    webhook_url: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PaymentDTO:
    id: UUID
    amount: Decimal
    currency: payment_processor.constants.payments.Currency
    description: str
    metadata: JsonObject
    status: payment_processor.constants.payments.PaymentStatus
    idempotency_key: str
    request_hash: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
    gateway_reference: str | None
    failure_code: str | None
    webhook_event_id: UUID | None
    webhook_payload: JsonObject | None
    webhook_status: payment_processor.constants.payments.WebhookStatus
    webhook_attempts: int
    webhook_delivered_at: datetime | None
    webhook_last_error: str | None
    processing_attempt: int
    expected_event_id: UUID
    next_attempt_at: datetime
    lease_token: UUID | None
    lease_expires_at: datetime | None
    processing_exhausted_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProcessingEventDTO:
    event_id: UUID
    payment_id: UUID
    attempt: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class GatewayResultDTO:
    status: payment_processor.constants.payments.TerminalPaymentStatus
    reference: str
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class WebhookNotificationDTO:
    event_id: UUID
    payment_id: UUID
    status: payment_processor.constants.payments.TerminalPaymentStatus
    amount: Decimal
    currency: payment_processor.constants.payments.Currency
    processed_at: datetime
    failure_code: str | None
