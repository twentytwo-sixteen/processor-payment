from datetime import datetime
from typing import Protocol
from uuid import UUID

from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxMessageDTO, OutboxStatsDTO


class OutboxDAOProtocol(Protocol):
    async def create_outbox_message(self, message: OutboxMessageDTO) -> None: ...
    async def claim_outbox_messages_exclusive(
        self,
        limit: int,
        token: UUID,
        lease_seconds: int,
    ) -> list[OutboxMessageDTO]: ...
    async def mark_outbox_message_published(self, message_id: UUID, token: UUID) -> bool: ...
    async def record_outbox_message_publish_failure(
        self,
        message_id: UUID,
        token: UUID,
        error_code: str,
        available_at: datetime,
    ) -> None: ...
    async def get_outbox_stats(self) -> OutboxStatsDTO: ...


class PublisherProtocol(Protocol):
    async def publish(self, message: OutboxMessageDTO) -> None: ...
