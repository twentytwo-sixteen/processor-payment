import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette import status
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

import payment_processor.constants.http
from payment_processor.apps.core.observability import UNEXPECTED_ERRORS
from payment_processor.apps.core.services.errors import (
    PermanentServiceIntegrationError,
    RetryableServiceIntegrationError,
    ServiceConflictError,
    ServiceError,
    ServiceNotFoundError,
    ServiceUnavailableError,
    ServiceValidationError,
)

logger = logging.getLogger(__name__)

SERVICE_ERROR_TYPE_TO_HTTP_STATUS_MAP: dict[type[ServiceError], int] = {
    ServiceNotFoundError: status.HTTP_404_NOT_FOUND,
    ServiceConflictError: status.HTTP_409_CONFLICT,
    ServiceValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ServiceUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    RetryableServiceIntegrationError: status.HTTP_503_SERVICE_UNAVAILABLE,
    PermanentServiceIntegrationError: status.HTTP_502_BAD_GATEWAY,
}


def _service_http_status(error: ServiceError) -> int:
    for error_type in type(error).__mro__:
        http_status = SERVICE_ERROR_TYPE_TO_HTTP_STATUS_MAP.get(error_type)
        if http_status is not None:
            return http_status
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def error_response(http_status: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        headers={payment_processor.constants.http.HTTP_HEADER_REQUEST_ID: request_id},
        status_code=http_status,
        content={'error': {'code': code, 'message': message, 'request_id': request_id}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        http_status = _service_http_status(exc)
        logger.log(
            logging.ERROR if http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR else logging.INFO,
            'api_error',
            extra={'error_code': exc.code, 'request_id': request.state.request_id},
            exc_info=exc if http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR else None,
        )
        return error_response(http_status, exc.code, exc.message, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            payment_processor.constants.http.HTTP_ERROR_VALIDATION_CODE,
            payment_processor.constants.http.HTTP_ERROR_VALIDATION_MESSAGE,
            request.state.request_id,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(
            exc.status_code,
            payment_processor.constants.http.HTTP_ERROR_REQUEST_CODE,
            payment_processor.constants.http.HTTP_ERROR_REQUEST_MESSAGE,
            request.state.request_id,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        UNEXPECTED_ERRORS.labels(boundary='api').inc()
        logger.exception(
            'unexpected_api_error',
            extra={'exception_type': type(exc).__name__, 'request_id': request.state.request_id},
            exc_info=exc,
        )
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            payment_processor.constants.http.HTTP_ERROR_INTERNAL_CODE,
            payment_processor.constants.http.HTTP_ERROR_INTERNAL_MESSAGE,
            request.state.request_id,
        )
