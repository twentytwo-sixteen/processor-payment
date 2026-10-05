import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

import payment_processor.constants.payments
from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.core.services.errors import ServiceIntegrationError
from payment_processor.apps.core.services.transactions import service_contract_errors, service_integration_errors
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.payments.dtos.payment_dto import (
    GatewayResultDTO,
    PaymentDTO,
    ProcessingEventDTO,
    WebhookNotificationDTO,
)
from payment_processor.apps.payments.errors.base import LeaseBusyError
from payment_processor.apps.payments.ports import GatewayProtocol, PaymentContractMapperProtocol
from payment_processor.apps.payments.services.schedule_payment_retry_service import SchedulePaymentRetryService
from payment_processor.apps.payments.services.send_payment_webhook_service import SendPaymentWebhookService
from payment_processor.apps.payments.services.transactions import payment_unit_of_work

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessPaymentService:
    _uow_factory: UnitOfWorkFactory
    _gateway: GatewayProtocol
    _contracts: PaymentContractMapperProtocol
    _webhook: SendPaymentWebhookService
    _retry: SchedulePaymentRetryService
    _lease_seconds: int

    async def execute(self, event: ProcessingEventDTO) -> None:
        token = uuid4()
        payment = await self._claim_payment(event, token)
        if payment is None:
            return
        if payment.status == payment_processor.constants.payments.PaymentStatus.PENDING:
            try:
                result = await self._call_gateway(payment)
            except ServiceIntegrationError as error:
                await self._schedule_retry(event, token, error)
                return
            payment = await self._save_gateway_result(payment, token, result)
        try:
            await self._webhook.execute(payment=payment, token=token)
        except ServiceIntegrationError as error:
            await self._schedule_retry(event, token, error)
            return
        logger.info(
            'payment_processed',
            extra={
                'payment_id': str(payment.id),
                'event_id': str(event.event_id),
                'attempt': event.attempt,
                'status': payment.status,
            },
        )

    async def _claim_payment(self, event: ProcessingEventDTO, token: UUID) -> PaymentDTO | None:
        async with payment_unit_of_work(self._uow_factory) as uow:
            payment = await uow.payments.claim_payment_for_processing_exclusive(
                event=event,
                token=token,
                lease_seconds=self._lease_seconds,
            )
            if payment is not None:
                return payment
            existing = await uow.payments.get_payment_by_id(payment_id=event.payment_id)
            if (
                existing.expected_event_id != event.event_id
                or existing.processing_attempt != event.attempt
                or existing.webhook_status == payment_processor.constants.payments.WebhookStatus.DELIVERED
                or existing.processing_exhausted_at is not None
            ):
                return None
            raise LeaseBusyError()

    async def _call_gateway(self, payment: PaymentDTO) -> GatewayResultDTO:
        with service_integration_errors():
            return await self._gateway.process(payment.id, payment.amount, payment.currency)

    async def _save_gateway_result(self, payment: PaymentDTO, token: UUID, result: GatewayResultDTO) -> PaymentDTO:
        notification = WebhookNotificationDTO(
            event_id=uuid4(),
            payment_id=payment.id,
            status=result.status,
            amount=payment.amount,
            currency=payment.currency,
            processed_at=utcnow(),
            failure_code=result.failure_code,
        )
        with service_contract_errors():
            payload = self._contracts.encode_webhook(notification)
        async with payment_unit_of_work(self._uow_factory) as uow:
            return await uow.payments.update_payment_gateway_result(
                payment_id=payment.id,
                token=token,
                result=result,
                notification=notification,
                payload=payload,
            )

    async def _schedule_retry(self, event: ProcessingEventDTO, token: UUID, error: ServiceIntegrationError) -> None:
        await self._retry.execute(event=event, token=token, error=error)
        logger.warning(
            'payment_attempt_failed',
            extra={
                'payment_id': str(event.payment_id),
                'event_id': str(event.event_id),
                'attempt': event.attempt,
                'error_code': error.reason_code,
                'http_status': error.http_status,
            },
            exc_info=error,
        )
