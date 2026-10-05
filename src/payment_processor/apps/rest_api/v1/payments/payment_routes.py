from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Security, status
from fastapi.security import APIKeyHeader

import payment_processor.constants.http
import payment_processor.constants.payments
from payment_processor.apps.rest_api.v1.payments.payment_dependencies import (
    CreatePaymentDependency,
    GetPaymentDependency,
)
from payment_processor.apps.rest_api.v1.payments.payment_schemas import (
    CreatePaymentRequest,
    PaymentAcceptedResponse,
    PaymentResponse,
)

router = APIRouter(
    prefix='/api/v1/payments',
    tags=['payments'],
    dependencies=[
        Security(APIKeyHeader(name=payment_processor.constants.http.HTTP_HEADER_API_KEY, auto_error=False)),
    ],
)


@router.post('', status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAcceptedResponse)
async def create_payment(
    body: CreatePaymentRequest,
    service: CreatePaymentDependency,
    idempotency_key: Annotated[
        str,
        Header(
            alias=payment_processor.constants.http.HTTP_HEADER_IDEMPOTENCY_KEY,
            min_length=payment_processor.constants.payments.PAYMENT_IDEMPOTENCY_KEY_MIN_LENGTH,
            max_length=payment_processor.constants.payments.PAYMENT_IDEMPOTENCY_KEY_MAX_LENGTH,
        ),
    ],
) -> PaymentAcceptedResponse:
    payment = await service.execute(command=body.to_dto(idempotency_key=idempotency_key))
    return PaymentAcceptedResponse(payment_id=payment.id, status=payment.status, created_at=payment.created_at)


@router.get('/{payment_id}', response_model=PaymentResponse)
async def get_payment(payment_id: UUID, service: GetPaymentDependency) -> PaymentResponse:
    payment = await service.execute(payment_id=payment_id)
    return PaymentResponse.from_dto(payment=payment)
