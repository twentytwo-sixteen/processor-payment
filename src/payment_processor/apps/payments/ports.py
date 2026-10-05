from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

import payment_processor.constants.payments
from payment_processor.apps.core.types import JsonObject
from payment_processor.apps.payments.dtos.payment_dto import (
    CreatePaymentDTO,
    GatewayResultDTO,
    PaymentDTO,
    ProcessingEventDTO,
    WebhookNotificationDTO,
)


class PaymentDAOProtocol(Protocol):
    async def create_pending_payment(
        self,
        *,
        payment_id: UUID,
        command: CreatePaymentDTO,
        request_hash: str,
        event: ProcessingEventDTO,
    ) -> PaymentDTO | None: ...
    async def get_payment_by_id(self, payment_id: UUID) -> PaymentDTO: ...
    async def get_payment_by_idempotency_key(self, idempotency_key: str) -> PaymentDTO: ...
    async def claim_payment_for_processing_exclusive(
        self,
        event: ProcessingEventDTO,
        token: UUID,
        lease_seconds: int,
    ) -> PaymentDTO | None: ...
    async def update_payment_gateway_result(
        self,
        payment_id: UUID,
        token: UUID,
        result: GatewayResultDTO,
        notification: WebhookNotificationDTO,
        payload: JsonObject,
    ) -> PaymentDTO: ...
    async def reserve_payment_webhook_attempt(self, payment_id: UUID, token: UUID) -> PaymentDTO | None: ...
    async def mark_payment_webhook_delivered(self, payment_id: UUID, token: UUID) -> None: ...
    async def update_payment_retry_schedule(
        self,
        payment_id: UUID,
        token: UUID,
        event: ProcessingEventDTO,
        available_at: datetime,
        error_code: str,
    ) -> None: ...
    async def mark_payment_processing_exhausted(
        self,
        payment_id: UUID,
        token: UUID,
        error_code: str,
        webhook_status: payment_processor.constants.payments.WebhookStatus,
    ) -> None: ...


class GatewayProtocol(Protocol):
    async def process(self, payment_id: UUID, amount: Decimal, currency: str) -> GatewayResultDTO: ...


class WebhookClientProtocol(Protocol):
    async def send(self, url: str, event_id: UUID, payload: JsonObject) -> None: ...


class PaymentContractMapperProtocol(Protocol):
    def encode_processing(self, event: ProcessingEventDTO) -> JsonObject: ...
    def encode_webhook(self, notification: WebhookNotificationDTO) -> JsonObject: ...
