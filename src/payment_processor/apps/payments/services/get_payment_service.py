from dataclasses import dataclass
from uuid import UUID

from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.payments.dtos.payment_dto import PaymentDTO
from payment_processor.apps.payments.services.transactions import payment_unit_of_work


@dataclass(slots=True)
class GetPaymentService:
    _uow_factory: UnitOfWorkFactory

    async def execute(self, payment_id: UUID) -> PaymentDTO:
        async with payment_unit_of_work(self._uow_factory) as uow:
            return await uow.payments.get_payment_by_id(payment_id=payment_id)
