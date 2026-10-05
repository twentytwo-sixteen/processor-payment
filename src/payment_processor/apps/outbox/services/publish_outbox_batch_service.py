import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import payment_processor.constants.outbox
from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.core.services.errors import RetryableServiceIntegrationError, ServiceUnavailableError
from payment_processor.apps.core.services.transactions import service_integration_errors, service_unit_of_work
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxMessageDTO
from payment_processor.apps.outbox.ports import PublisherProtocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublishOutboxBatchService:
    _uow_factory: UnitOfWorkFactory
    _publisher: PublisherProtocol
    _batch_size: int
    _concurrency: int
    _lease_seconds: int

    async def execute(self) -> int:
        token = uuid4()
        async with service_unit_of_work(self._uow_factory) as uow:
            messages = await uow.outbox.claim_outbox_messages_exclusive(
                limit=self._batch_size,
                token=token,
                lease_seconds=self._lease_seconds,
            )
        semaphore = asyncio.Semaphore(self._concurrency)
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._publish_one(message, token, semaphore)) for message in messages]
        return sum(task.result() for task in tasks)

    async def _publish_one(self, message: OutboxMessageDTO, token: UUID, semaphore: asyncio.Semaphore) -> bool:
        async with semaphore:
            try:
                await self._publish_to_broker(message)
            except RetryableServiceIntegrationError as error:
                await self._schedule_retry(message, token, error)
                return False
            return await self._mark_published(message, token)

    async def _publish_to_broker(self, message: OutboxMessageDTO) -> None:
        with service_integration_errors():
            await self._publisher.publish(message)

    async def _schedule_retry(
        self,
        message: OutboxMessageDTO,
        token: UUID,
        error: RetryableServiceIntegrationError,
    ) -> None:
        backoff = min(
            payment_processor.constants.outbox.OUTBOX_RETRY_MAX_SECONDS,
            payment_processor.constants.outbox.OUTBOX_RETRY_BACKOFF_MULTIPLIER
            ** min(
                message.publish_attempts,
                payment_processor.constants.outbox.OUTBOX_RETRY_MAX_EXPONENT,
            ),
        )
        try:
            async with service_unit_of_work(self._uow_factory) as uow:
                await uow.outbox.record_outbox_message_publish_failure(
                    message_id=message.id,
                    token=token,
                    error_code=error.reason_code,
                    available_at=utcnow() + timedelta(seconds=backoff),
                )
        except ServiceUnavailableError as storage_error:
            self._log_storage_failure(message.id, storage_error)
        logger.warning(
            'outbox_publish_failed',
            extra={'event_id': str(message.id), 'error_code': error.reason_code},
            exc_info=error,
        )

    async def _mark_published(self, message: OutboxMessageDTO, token: UUID) -> bool:
        try:
            async with service_unit_of_work(self._uow_factory) as uow:
                return await uow.outbox.mark_outbox_message_published(message_id=message.id, token=token)
        except ServiceUnavailableError as error:
            self._log_storage_failure(message.id, error)
            return False

    @staticmethod
    def _log_storage_failure(event_id: UUID, error: ServiceUnavailableError) -> None:
        logger.error(
            'outbox_storage_unavailable',
            extra={'event_id': str(event_id), 'error_code': error.code},
            exc_info=error,
        )
