from typing import Annotated

from fastapi import Depends

from payment_processor.apps.payments.services.create_payment_service import CreatePaymentService
from payment_processor.apps.payments.services.get_payment_service import GetPaymentService
from payment_processor.apps.rest_api.dependencies import RuntimeDependency


async def get_create_payment_service(runtime: RuntimeDependency) -> CreatePaymentService:
    return runtime.create_payment


async def get_get_payment_service(runtime: RuntimeDependency) -> GetPaymentService:
    return runtime.get_payment


CreatePaymentDependency = Annotated[CreatePaymentService, Depends(get_create_payment_service)]
GetPaymentDependency = Annotated[GetPaymentService, Depends(get_get_payment_service)]
