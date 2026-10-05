from dataclasses import dataclass

from payment_processor.apps.core.database.ports import UnitOfWorkFactory
from payment_processor.apps.core.services.transactions import service_unit_of_work
from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxStatsDTO


@dataclass(slots=True)
class GetOutboxStatsService:
    _uow_factory: UnitOfWorkFactory

    async def execute(self) -> OutboxStatsDTO:
        async with service_unit_of_work(self._uow_factory) as uow:
            return await uow.outbox.get_outbox_stats()
