from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

import payment_processor.constants.payments


class PaymentResultWebhook(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = payment_processor.constants.payments.PAYMENT_SCHEMA_VERSION
    event_type: Literal['payment.processed'] = payment_processor.constants.payments.PAYMENT_EVENT_PROCESSED
    event_id: UUID
    payment_id: UUID
    status: Literal['succeeded', 'failed']
    amount: Decimal
    currency: payment_processor.constants.payments.Currency
    processed_at: AwareDatetime
    failure_code: str | None
