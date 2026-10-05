from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from payment_processor.apps.core.database.errors import translate_data_errors


class DatabaseHealthDAO:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @translate_data_errors
    async def check_database_connection(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(select(1))
