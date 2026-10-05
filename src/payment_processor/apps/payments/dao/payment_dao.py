from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, Update, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

import payment_processor.constants.payments
from payment_processor.apps.core.database.errors import translate_data_errors
from payment_processor.apps.core.errors import DataNotFoundError, DataWriteConflictError
from payment_processor.apps.core.types import JsonObject
from payment_processor.apps.payments.dtos.payment_dto import (
    CreatePaymentDTO,
    GatewayResultDTO,
    PaymentDTO,
    ProcessingEventDTO,
    WebhookNotificationDTO,
)
from payment_processor.apps.payments.models import Payment


class PaymentDAO:
    class PaymentDoesNotExistException(DataNotFoundError):
        pass

    class PaymentWriteConflictError(DataWriteConflictError):
        pass

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _orm_to_dto(orm: Payment) -> PaymentDTO:
        return PaymentDTO(
            id=orm.id,
            amount=orm.amount,
            currency=payment_processor.constants.payments.Currency(orm.currency),
            description=orm.description,
            metadata=deepcopy(orm.metadata_json),
            status=payment_processor.constants.payments.PaymentStatus(orm.status),
            idempotency_key=orm.idempotency_key,
            request_hash=orm.request_hash,
            webhook_url=orm.webhook_url,
            created_at=orm.created_at,
            processed_at=orm.processed_at,
            gateway_reference=orm.gateway_reference,
            failure_code=orm.failure_code,
            webhook_event_id=orm.webhook_event_id,
            webhook_payload=deepcopy(orm.webhook_payload),
            webhook_status=payment_processor.constants.payments.WebhookStatus(orm.webhook_status),
            webhook_attempts=orm.webhook_attempts,
            webhook_delivered_at=orm.webhook_delivered_at,
            webhook_last_error=orm.webhook_last_error,
            processing_attempt=orm.processing_attempt,
            expected_event_id=orm.expected_event_id,
            next_attempt_at=orm.next_attempt_at,
            lease_token=orm.lease_token,
            lease_expires_at=orm.lease_expires_at,
            processing_exhausted_at=orm.processing_exhausted_at,
        )

    @translate_data_errors
    async def create_pending_payment(
        self,
        *,
        payment_id: UUID,
        command: CreatePaymentDTO,
        request_hash: str,
        event: ProcessingEventDTO,
    ) -> PaymentDTO | None:
        statement = (
            insert(Payment)
            .values(
                id=payment_id,
                amount=command.amount,
                currency=command.currency,
                description=command.description,
                metadata_json=command.metadata,
                status=payment_processor.constants.payments.PaymentStatus.PENDING,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                webhook_url=command.webhook_url,
                expected_event_id=event.event_id,
                next_attempt_at=event.occurred_at,
            )
            .on_conflict_do_nothing(index_elements=['idempotency_key'])
            .returning(Payment)
        )
        orm: Payment | None = (await self._session.scalars(statement)).one_or_none()
        return self._orm_to_dto(orm) if orm is not None else None

    @translate_data_errors
    async def get_payment_by_id(self, payment_id: UUID) -> PaymentDTO:
        return await self._get_one(select(Payment).where(Payment.id == payment_id))

    @translate_data_errors
    async def get_payment_by_idempotency_key(self, idempotency_key: str) -> PaymentDTO:
        return await self._get_one(select(Payment).where(Payment.idempotency_key == idempotency_key))

    @translate_data_errors
    async def claim_payment_for_processing_exclusive(
        self,
        event: ProcessingEventDTO,
        token: UUID,
        lease_seconds: int,
    ) -> PaymentDTO | None:
        statement = (
            update(Payment)
            .where(
                Payment.id == event.payment_id,
                Payment.expected_event_id == event.event_id,
                Payment.processing_attempt == event.attempt,
                Payment.processing_exhausted_at.is_(None),
                Payment.webhook_status != payment_processor.constants.payments.WebhookStatus.DELIVERED,
                Payment.next_attempt_at <= func.now(),
                or_(Payment.lease_token.is_(None), Payment.lease_expires_at <= func.now()),
            )
            .values(
                lease_token=token,
                lease_expires_at=func.now() + timedelta(seconds=lease_seconds),
                updated_at=func.now(),
            )
            .returning(Payment)
        )
        orm: Payment | None = (await self._session.scalars(statement)).one_or_none()
        return self._orm_to_dto(orm) if orm is not None else None

    @translate_data_errors
    async def update_payment_gateway_result(
        self,
        payment_id: UUID,
        token: UUID,
        result: GatewayResultDTO,
        notification: WebhookNotificationDTO,
        payload: JsonObject,
    ) -> PaymentDTO:
        statement = (
            self._leased_update(payment_id, token)
            .where(Payment.status == payment_processor.constants.payments.PaymentStatus.PENDING)
            .values(
                status=result.status,
                processed_at=notification.processed_at,
                gateway_reference=result.reference,
                failure_code=result.failure_code,
                webhook_event_id=notification.event_id,
                webhook_payload=payload,
                webhook_status=payment_processor.constants.payments.WebhookStatus.PENDING,
                updated_at=func.now(),
            )
            .returning(Payment)
        )
        orm: Payment | None = (await self._session.scalars(statement)).one_or_none()
        if orm is None:
            raise self.PaymentWriteConflictError()
        return self._orm_to_dto(orm)

    @translate_data_errors
    async def reserve_payment_webhook_attempt(self, payment_id: UUID, token: UUID) -> PaymentDTO | None:
        statement = (
            self._leased_update(payment_id, token)
            .where(
                Payment.webhook_attempts < payment_processor.constants.payments.PAYMENT_MAX_ATTEMPTS,
                Payment.webhook_status == payment_processor.constants.payments.WebhookStatus.PENDING,
            )
            .values(webhook_attempts=Payment.webhook_attempts + 1, updated_at=func.now())
            .returning(Payment)
        )
        orm: Payment | None = (await self._session.scalars(statement)).one_or_none()
        return self._orm_to_dto(orm) if orm is not None else None

    @translate_data_errors
    async def mark_payment_webhook_delivered(self, payment_id: UUID, token: UUID) -> None:
        statement = self._leased_update(payment_id, token).values(
            webhook_status=payment_processor.constants.payments.WebhookStatus.DELIVERED,
            webhook_delivered_at=func.now(),
            webhook_last_error=None,
            lease_token=None,
            lease_expires_at=None,
            updated_at=func.now(),
        )
        await self._require_updated(statement)

    @translate_data_errors
    async def update_payment_retry_schedule(
        self,
        payment_id: UUID,
        token: UUID,
        event: ProcessingEventDTO,
        available_at: datetime,
        error_code: str,
    ) -> None:
        statement = self._leased_update(payment_id, token).values(
            processing_attempt=event.attempt,
            expected_event_id=event.event_id,
            next_attempt_at=available_at,
            webhook_last_error=error_code,
            lease_token=None,
            lease_expires_at=None,
            updated_at=func.now(),
        )
        await self._require_updated(statement)

    @translate_data_errors
    async def mark_payment_processing_exhausted(
        self,
        payment_id: UUID,
        token: UUID,
        error_code: str,
        webhook_status: payment_processor.constants.payments.WebhookStatus,
    ) -> None:
        statement = self._leased_update(payment_id, token).values(
            processing_exhausted_at=func.now(),
            webhook_status=webhook_status,
            webhook_last_error=error_code,
            lease_token=None,
            lease_expires_at=None,
            updated_at=func.now(),
        )
        await self._require_updated(statement)

    async def _get_one(self, statement: Select[tuple[Payment]]) -> PaymentDTO:
        orm = (await self._session.scalars(statement)).one_or_none()
        if orm is None:
            raise self.PaymentDoesNotExistException()
        return self._orm_to_dto(orm)

    async def _require_updated(self, statement: Update) -> None:
        payment_id: UUID | None = await self._session.scalar(statement.returning(Payment.id))
        if payment_id is None:
            raise self.PaymentWriteConflictError()

    @staticmethod
    def _leased_update(payment_id: UUID, token: UUID) -> Update:

        return update(Payment).where(
            Payment.id == payment_id,
            Payment.lease_token == token,
            Payment.lease_expires_at > func.now(),
        )
