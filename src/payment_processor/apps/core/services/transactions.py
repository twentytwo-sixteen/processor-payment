from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from payment_processor.apps.core.database.ports import UnitOfWork, UnitOfWorkFactory
from payment_processor.apps.core.errors import (
    ContractEncodingError,
    DataAccessError,
    DataIntegrityError,
    DataNotFoundError,
    DataWriteConflictError,
    PermanentIntegrationError,
    RetryableIntegrationError,
)
from payment_processor.apps.core.services.errors import (
    PermanentServiceIntegrationError,
    RetryableServiceIntegrationError,
    ServiceConflictError,
    ServiceContractError,
    ServiceIntegrityError,
    ServiceNotFoundError,
    ServiceUnavailableError,
)


@contextmanager
def service_contract_errors() -> Iterator[None]:
    try:
        yield
    except ContractEncodingError as error:
        raise ServiceContractError() from error


@contextmanager
def service_integration_errors() -> Iterator[None]:

    try:
        yield
    except RetryableIntegrationError as error:
        raise RetryableServiceIntegrationError(reason_code=error.code, http_status=error.http_status) from error
    except PermanentIntegrationError as error:
        raise PermanentServiceIntegrationError(reason_code=error.code, http_status=error.http_status) from error


@asynccontextmanager
async def service_data_errors(
    *,
    not_found_error: type[ServiceNotFoundError] = ServiceNotFoundError,
    conflict_error: type[ServiceConflictError] = ServiceConflictError,
) -> AsyncIterator[None]:

    try:
        yield
    except DataAccessError as error:
        raise ServiceUnavailableError() from error
    except DataIntegrityError as error:
        raise ServiceIntegrityError() from error
    except DataNotFoundError as error:
        raise not_found_error() from error
    except DataWriteConflictError as error:
        raise conflict_error() from error


@asynccontextmanager
async def service_unit_of_work(
    factory: UnitOfWorkFactory,
    *,
    not_found_error: type[ServiceNotFoundError] = ServiceNotFoundError,
    conflict_error: type[ServiceConflictError] = ServiceConflictError,
) -> AsyncIterator[UnitOfWork]:
    async with service_data_errors(not_found_error=not_found_error, conflict_error=conflict_error), factory() as uow:
        yield uow
