from typing import cast

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticSerializationError

from payment_processor.apps.core.errors import ContractEncodingError
from payment_processor.apps.core.types import JsonObject
from payment_processor.apps.payments.contracts.processing_event import PaymentProcessingRequested
from payment_processor.apps.payments.contracts.result_webhook import PaymentResultWebhook
from payment_processor.apps.payments.dtos.payment_dto import ProcessingEventDTO, WebhookNotificationDTO


class PaymentContractMapper:
    def encode_processing(self, event: ProcessingEventDTO) -> JsonObject:
        return self._encode(PaymentProcessingRequested, event)

    def encode_webhook(self, notification: WebhookNotificationDTO) -> JsonObject:
        return self._encode(PaymentResultWebhook, notification)

    @staticmethod
    def _encode(contract: type[BaseModel], dto: ProcessingEventDTO | WebhookNotificationDTO) -> JsonObject:
        try:
            model = contract.model_validate(dto, from_attributes=True)
            return cast(JsonObject, model.model_dump(mode='json'))
        except (ValidationError, PydanticSerializationError) as error:
            raise ContractEncodingError() from error
