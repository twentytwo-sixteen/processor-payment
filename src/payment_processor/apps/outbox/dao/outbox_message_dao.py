from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Update, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from payment_processor.apps.core.database.errors import translate_data_errors
from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxMessageDTO, OutboxStatsDTO
from payment_processor.apps.outbox.models import OutboxMessage


class OutboxMessageDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _orm_to_dto(orm: OutboxMessage) -> OutboxMessageDTO:
        return OutboxMessageDTO(
            id=orm.id,
            payment_id=orm.payment_id,
            event_type=orm.event_type,
            attempt=orm.attempt,
            exchange=orm.exchange,
            routing_key=orm.routing_key,
            payload=deepcopy(orm.payload),
            available_at=orm.available_at,
            lease_token=orm.lease_token,
            publish_attempts=orm.publish_attempts,
        )

    @translate_data_errors
    async def create_outbox_message(self, message: OutboxMessageDTO) -> None:
        statement = insert(OutboxMessage).values(
            id=message.id,
            payment_id=message.payment_id,
            event_type=message.event_type,
            attempt=message.attempt,
            exchange=message.exchange,
            routing_key=message.routing_key,
            payload=message.payload,
            available_at=message.available_at,
        )
        await self._session.execute(statement)

    @translate_data_errors
    async def claim_outbox_messages_exclusive(
        self,
        limit: int,
        token: UUID,
        lease_seconds: int,
    ) -> list[OutboxMessageDTO]:
        candidates = (
            select(OutboxMessage.id)
            .where(
                OutboxMessage.published_at.is_(None),
                OutboxMessage.available_at <= func.now(),
                or_(OutboxMessage.lease_token.is_(None), OutboxMessage.lease_expires_at <= func.now()),
            )
            .order_by(OutboxMessage.available_at, OutboxMessage.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        statement = (
            update(OutboxMessage)
            .where(OutboxMessage.id.in_(candidates))
            .values(
                lease_token=token,
                lease_expires_at=func.now() + timedelta(seconds=lease_seconds),
                publish_attempts=OutboxMessage.publish_attempts + 1,
            )
            .returning(OutboxMessage)
        )
        messages = await self._session.scalars(statement)
        return [self._orm_to_dto(orm) for orm in messages]

    @translate_data_errors
    async def mark_outbox_message_published(self, message_id: UUID, token: UUID) -> bool:
        statement = (
            self._claimed_update(message_id, token)
            .where(OutboxMessage.lease_expires_at > func.now())
            .values(published_at=func.now(), lease_token=None, lease_expires_at=None, last_error=None)
            .returning(OutboxMessage.id)
        )
        return await self._session.scalar(statement) is not None

    @translate_data_errors
    async def record_outbox_message_publish_failure(
        self,
        message_id: UUID,
        token: UUID,
        error_code: str,
        available_at: datetime,
    ) -> None:
        statement = self._claimed_update(message_id, token).values(
            last_error=error_code,
            available_at=available_at,
            lease_token=None,
            lease_expires_at=None,
        )
        await self._session.execute(statement)

    @translate_data_errors
    async def get_outbox_stats(self) -> OutboxStatsDTO:
        statement = select(func.count(OutboxMessage.id), func.min(OutboxMessage.created_at)).where(
            OutboxMessage.published_at.is_(None),
        )
        pending, oldest_created_at = (await self._session.execute(statement)).one()
        return OutboxStatsDTO(pending=pending, oldest_created_at=oldest_created_at)

    @staticmethod
    def _claimed_update(message_id: UUID, token: UUID) -> Update:
        return update(OutboxMessage).where(OutboxMessage.id == message_id, OutboxMessage.lease_token == token)
