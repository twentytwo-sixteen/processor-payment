from contextlib import AbstractAsyncContextManager

from payment_processor.apps.core.database.ports import UnitOfWork, UnitOfWorkFactory
from payment_processor.apps.core.services.transactions import service_unit_of_work
from payment_processor.apps.payments.errors.base import LeaseLostError, PaymentNotFoundError


def payment_unit_of_work(factory: UnitOfWorkFactory) -> AbstractAsyncContextManager[UnitOfWork]:
    return service_unit_of_work(factory, not_found_error=PaymentNotFoundError, conflict_error=LeaseLostError)
