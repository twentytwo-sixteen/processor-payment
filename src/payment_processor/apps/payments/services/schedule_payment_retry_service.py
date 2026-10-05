from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import payment_processor.constants.payments
from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.core.services.errors import ServiceIntegrationError
from payment_processor.apps.core.services.transactions import service_contract_errors
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxMessageDTO
from payment_processor.apps.payments.dtos.payment_dto import PaymentDTO, ProcessingEventDTO
from payment_processor.apps.payments.errors.base import LeaseLostError
from payment_processor.apps.payments.ports import PaymentContractMapperProtocol
from payment_processor.apps.payments.services.transactions import payment_unit_of_work


@dataclass(slots=True)
class SchedulePaymentRetryService:
    _uow_factory: UnitOfWorkFactory
    _contracts: PaymentContractMapperProtocol
    _retry_base: float

    async def execute(self, event: ProcessingEventDTO, token: UUID, error: ServiceIntegrationError) -> None:
        now = utcnow()
        async with payment_unit_of_work(self._uow_factory) as uow:
            payment = await uow.payments.get_payment_by_id(payment_id=event.payment_id)
            if payment.lease_token != token:
                raise LeaseLostError()
            exhausted = (
                not error.retryable
                or event.attempt >= payment_processor.constants.payments.PAYMENT_MAX_ATTEMPTS
                or payment.webhook_attempts >= payment_processor.constants.payments.PAYMENT_MAX_ATTEMPTS
            )
            if exhausted:
                webhook_status = (
                    payment_processor.constants.payments.WebhookStatus.NOT_READY
                    if payment.status == payment_processor.constants.payments.PaymentStatus.PENDING
                    else payment_processor.constants.payments.WebhookStatus.EXHAUSTED
                )
                await uow.payments.mark_payment_processing_exhausted(
                    payment_id=payment.id,
                    token=token,
                    error_code=error.reason_code,
                    webhook_status=webhook_status,
                )
                message = self._dead_letter_message(payment, event, error.reason_code, now)
            else:
                next_event = ProcessingEventDTO(
                    event_id=uuid4(),
                    payment_id=payment.id,
                    attempt=event.attempt + 1,
                    occurred_at=now,
                )
                retry_delay = (
                    self._retry_base
                    * payment_processor.constants.payments.PAYMENT_RETRY_BACKOFF_MULTIPLIER
                    ** (event.attempt - payment_processor.constants.payments.PAYMENT_PROCESSING_ATTEMPT_INITIAL)
                )
                available_at = now + timedelta(seconds=retry_delay)
                await uow.payments.update_payment_retry_schedule(
                    payment_id=payment.id,
                    token=token,
                    event=next_event,
                    available_at=available_at,
                    error_code=error.reason_code,
                )
                message = self._retry_message(next_event, available_at)
            await uow.outbox.create_outbox_message(message=message)

    def _retry_message(self, event: ProcessingEventDTO, available_at: datetime) -> OutboxMessageDTO:
        with service_contract_errors():
            payload = self._contracts.encode_processing(event)
        return OutboxMessageDTO(
            id=event.event_id,
            payment_id=event.payment_id,
            event_type=payment_processor.constants.payments.PAYMENT_EVENT_PROCESSING_REQUESTED,
            attempt=event.attempt,
            exchange=payment_processor.constants.payments.PAYMENT_EXCHANGE,
            routing_key=payment_processor.constants.payments.PAYMENT_QUEUE,
            payload=payload,
            available_at=available_at,
        )

    def _dead_letter_message(
        self,
        payment: PaymentDTO,
        event: ProcessingEventDTO,
        error_code: str,
        available_at: datetime,
    ) -> OutboxMessageDTO:
        with service_contract_errors():
            payload = self._contracts.encode_processing(event)
        payload.update(
            error_code=error_code,
            stage='gateway'
            if payment.status == payment_processor.constants.payments.PaymentStatus.PENDING
            else 'webhook',
            original_event_id=str(event.event_id),
        )
        return OutboxMessageDTO(
            id=uuid4(),
            payment_id=payment.id,
            event_type=payment_processor.constants.payments.PAYMENT_EVENT_PROCESSING_EXHAUSTED,
            attempt=event.attempt,
            exchange=payment_processor.constants.payments.PAYMENT_DEAD_EXCHANGE,
            routing_key=payment_processor.constants.payments.PAYMENT_DEAD_ROUTING_KEY,
            payload=payload,
            available_at=available_at,
        )
