from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_processor.apps.core.database.errors import translate_data_errors
from payment_processor.apps.outbox.dao.outbox_message_dao import OutboxMessageDAO
from payment_processor.apps.outbox.ports import OutboxDAOProtocol
from payment_processor.apps.payments.dao.payment_dao import PaymentDAO
from payment_processor.apps.payments.ports import PaymentDAOProtocol


class SqlAlchemyUnitOfWork:
    payments: PaymentDAOProtocol
    outbox: OutboxDAOProtocol

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._transaction: AbstractAsyncContextManager[AsyncSession] = factory.begin()

    @translate_data_errors
    async def __aenter__(self) -> Self:
        session = await self._transaction.__aenter__()
        self.payments = PaymentDAO(session)
        self.outbox = OutboxMessageDAO(session)
        return self

    @translate_data_errors
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._transaction.__aexit__(exc_type, exc, traceback)
