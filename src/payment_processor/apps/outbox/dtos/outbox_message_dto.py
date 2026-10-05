from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from payment_processor.apps.core.types import JsonObject


@dataclass(frozen=True, slots=True)
class OutboxMessageDTO:
    id: UUID
    payment_id: UUID
    event_type: str
    attempt: int
    exchange: str
    routing_key: str
    payload: JsonObject
    available_at: datetime
    lease_token: UUID | None = None
    publish_attempts: int = 0


@dataclass(frozen=True, slots=True)
class OutboxStatsDTO:
    pending: int
    oldest_created_at: datetime | None
