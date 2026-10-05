import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

import payment_processor.constants.payments
from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.core.services.transactions import service_contract_errors
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxMessageDTO
from payment_processor.apps.payments.dtos.payment_dto import CreatePaymentDTO, PaymentDTO, ProcessingEventDTO
from payment_processor.apps.payments.dtos.webhook_destination_policy_dto import WebhookDestinationPolicyDTO
from payment_processor.apps.payments.errors.base import (
    IdempotencyConflictError,
    PaymentRuleViolationError,
    PaymentValidationError,
    WebhookDestinationError,
    WebhookURLRejectedError,
)
from payment_processor.apps.payments.ports import PaymentContractMapperProtocol
from payment_processor.apps.payments.services.transactions import payment_unit_of_work
from payment_processor.apps.payments.specifications.payment_specification import PaymentSpecification
from payment_processor.apps.payments.specifications.webhook_destination_specification import (
    WebhookDestinationSpecification,
)


@dataclass(slots=True)
class CreatePaymentService:
    _uow_factory: UnitOfWorkFactory
    _contracts: PaymentContractMapperProtocol
    _webhook_policy: WebhookDestinationPolicyDTO

    async def execute(self, command: CreatePaymentDTO) -> PaymentDTO:
        self._validate(command)
        fingerprint = self._request_fingerprint(command)
        event = ProcessingEventDTO(
            event_id=uuid4(),
            payment_id=uuid4(),
            attempt=payment_processor.constants.payments.PAYMENT_PROCESSING_ATTEMPT_INITIAL,
            occurred_at=utcnow(),
        )
        async with payment_unit_of_work(self._uow_factory) as uow:
            payment = await uow.payments.create_pending_payment(
                payment_id=event.payment_id,
                command=command,
                request_hash=fingerprint,
                event=event,
            )
            if payment is None:
                payment = await uow.payments.get_payment_by_idempotency_key(idempotency_key=command.idempotency_key)
                if payment.request_hash != fingerprint:
                    raise IdempotencyConflictError()
                return payment
            with service_contract_errors():
                payload = self._contracts.encode_processing(event)
            await uow.outbox.create_outbox_message(
                message=OutboxMessageDTO(
                    id=event.event_id,
                    payment_id=event.payment_id,
                    event_type=payment_processor.constants.payments.PAYMENT_EVENT_PROCESSING_REQUESTED,
                    attempt=event.attempt,
                    exchange=payment_processor.constants.payments.PAYMENT_EXCHANGE,
                    routing_key=payment_processor.constants.payments.PAYMENT_QUEUE,
                    payload=payload,
                    available_at=event.occurred_at,
                ),
            )
            return payment

    def _validate(self, command: CreatePaymentDTO) -> None:
        try:
            PaymentSpecification.affirm(command=command)
        except PaymentRuleViolationError as error:
            raise PaymentValidationError() from error
        try:
            WebhookDestinationSpecification.affirm(url=command.webhook_url, policy=self._webhook_policy)
        except WebhookDestinationError as error:
            raise WebhookURLRejectedError() from error

    @staticmethod
    def _request_fingerprint(command: CreatePaymentDTO) -> str:
        body = {
            'amount': format(command.amount, payment_processor.constants.payments.PAYMENT_AMOUNT_FINGERPRINT_FORMAT),
            'currency': command.currency,
            'description': command.description,
            'metadata': command.metadata,
            'webhook_url': command.webhook_url,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        return hashlib.sha256(encoded).hexdigest()
