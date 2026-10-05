from dataclasses import dataclass

from payment_processor.apps.core.database.ports import HealthDAOProtocol
from payment_processor.apps.core.services.transactions import service_data_errors


@dataclass(slots=True)
class HealthCheckService:
    _dao: HealthDAOProtocol

    async def execute(self) -> None:
        async with service_data_errors():
            await self._dao.check_database_connection()
