from dataclasses import dataclass
from uuid import UUID

import payment_processor.constants.payments
from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.core.services.transactions import service_integration_errors
from payment_processor.apps.payments.dtos.payment_dto import PaymentDTO
from payment_processor.apps.payments.errors.base import LeaseLostError, WebhookAttemptsExhaustedError
from payment_processor.apps.payments.ports import WebhookClientProtocol
from payment_processor.apps.payments.services.transactions import payment_unit_of_work


@dataclass(slots=True)
class SendPaymentWebhookService:
    _uow_factory: UnitOfWorkFactory
    _client: WebhookClientProtocol

    async def execute(self, payment: PaymentDTO, token: UUID) -> None:
        reserved = await self._reserve_attempt(payment.id, token)
        if reserved.webhook_event_id is None or reserved.webhook_payload is None:
            raise WebhookAttemptsExhaustedError()
        with service_integration_errors():
            await self._client.send(reserved.webhook_url, reserved.webhook_event_id, reserved.webhook_payload)
        async with payment_unit_of_work(self._uow_factory) as uow:
            await uow.payments.mark_payment_webhook_delivered(payment_id=reserved.id, token=token)

    async def _reserve_attempt(self, payment_id: UUID, token: UUID) -> PaymentDTO:
        async with payment_unit_of_work(self._uow_factory) as uow:
            reserved = await uow.payments.reserve_payment_webhook_attempt(payment_id=payment_id, token=token)
            if reserved is None:
                latest = await uow.payments.get_payment_by_id(payment_id=payment_id)
                if latest.webhook_attempts >= payment_processor.constants.payments.PAYMENT_MAX_ATTEMPTS:
                    raise WebhookAttemptsExhaustedError()
                raise LeaseLostError()
            return reserved
