from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from payment_processor.apps.outbox.ports import OutboxDAOProtocol
from payment_processor.apps.payments.ports import PaymentDAOProtocol


class HealthDAOProtocol(Protocol):
    async def check_database_connection(self) -> None: ...


class UnitOfWork(Protocol):
    payments: PaymentDAOProtocol
    outbox: OutboxDAOProtocol

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
