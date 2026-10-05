from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, JsonValue, field_validator

import payment_processor.constants.payment_errors
import payment_processor.constants.payments
from payment_processor.apps.payments.dtos.payment_dto import CreatePaymentDTO, PaymentDTO


class CreatePaymentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount: Annotated[
        Decimal,
        Field(
            gt=0,
            max_digits=payment_processor.constants.payments.PAYMENT_AMOUNT_MAX_DIGITS,
            decimal_places=payment_processor.constants.payments.PAYMENT_AMOUNT_DECIMAL_PLACES,
        ),
    ]
    currency: payment_processor.constants.payments.Currency
    description: str = Field(default='', max_length=payment_processor.constants.payments.PAYMENT_DESCRIPTION_MAX_LENGTH)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    webhook_url: AnyHttpUrl

    @field_validator('amount', mode='before', json_schema_input_type=str)
    @classmethod
    def require_decimal_string(cls, value: object) -> object:
        if not isinstance(value, (str, Decimal)):
            raise ValueError(payment_processor.constants.payment_errors.PAYMENT_AMOUNT_STRING_REQUIRED_MESSAGE)
        return value

    def to_dto(self, idempotency_key: str) -> CreatePaymentDTO:
        return CreatePaymentDTO(
            amount=self.amount,
            currency=self.currency,
            description=self.description,
            metadata=self.metadata,
            webhook_url=str(self.webhook_url),
            idempotency_key=idempotency_key,
        )


class PaymentAcceptedResponse(BaseModel):
    payment_id: UUID
    status: payment_processor.constants.payments.PaymentStatus
    created_at: datetime


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, validate_by_name=True)
    payment_id: UUID = Field(validation_alias='id')
    amount: Decimal
    currency: payment_processor.constants.payments.Currency
    description: str
    metadata: dict[str, JsonValue]
    status: payment_processor.constants.payments.PaymentStatus
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
    failure_code: str | None
    webhook_status: payment_processor.constants.payments.WebhookStatus
    webhook_attempts: int
    webhook_delivered_at: datetime | None
    webhook_last_error: str | None
    processing_exhausted_at: datetime | None

    @classmethod
    def from_dto(cls, payment: PaymentDTO) -> 'PaymentResponse':
        return cls.model_validate(payment)
