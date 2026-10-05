from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps

from asyncpg import IntegrityConstraintViolationError, PostgresError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from payment_processor.apps.core.errors import DataAccessError, DataIntegrityError


def translate_data_errors[**P, T](method: Callable[P, Awaitable[T]]) -> Callable[P, Coroutine[None, None, T]]:
    @wraps(method)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await method(*args, **kwargs)
        except (IntegrityError, IntegrityConstraintViolationError) as exc:
            raise DataIntegrityError() from exc
        except (SQLAlchemyError, PostgresError, OSError, TimeoutError) as exc:
            raise DataAccessError() from exc

    return wrapped
