from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

import payment_processor.constants.payments
from payment_processor.apps.payments.dtos.payment_dto import ProcessingEventDTO


class PaymentProcessingRequested(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = payment_processor.constants.payments.PAYMENT_SCHEMA_VERSION
    event_id: UUID
    payment_id: UUID
    attempt: int = Field(
        ge=payment_processor.constants.payments.PAYMENT_PROCESSING_ATTEMPT_INITIAL,
        le=payment_processor.constants.payments.PAYMENT_MAX_ATTEMPTS,
    )
    occurred_at: AwareDatetime

    def to_dto(self) -> ProcessingEventDTO:
        return ProcessingEventDTO(
            event_id=self.event_id,
            payment_id=self.payment_id,
            attempt=self.attempt,
            occurred_at=self.occurred_at,
        )
