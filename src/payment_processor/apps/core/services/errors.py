from typing import ClassVar

import payment_processor.constants.errors
from payment_processor.apps.core.errors import ApplicationError


class ServiceError(ApplicationError):
    code = payment_processor.constants.errors.SERVICE_ERROR_CODE


class ServiceUnavailableError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_UNAVAILABLE_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_UNAVAILABLE_ERROR_MESSAGE


class ServiceIntegrityError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_INTEGRITY_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_INTEGRITY_ERROR_MESSAGE


class ServiceContractError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_CONTRACT_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_CONTRACT_ERROR_MESSAGE


class ServiceNotFoundError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_NOT_FOUND_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_NOT_FOUND_ERROR_MESSAGE


class ServiceConflictError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_CONFLICT_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_CONFLICT_ERROR_MESSAGE


class ServiceValidationError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_VALIDATION_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_VALIDATION_ERROR_MESSAGE


class ServiceIntegrationError(ServiceError):
    code = payment_processor.constants.errors.SERVICE_INTEGRATION_ERROR_CODE
    message = payment_processor.constants.errors.SERVICE_INTEGRATION_ERROR_MESSAGE
    retryable: ClassVar[bool] = False

    def __init__(self, *, reason_code: str | None = None, http_status: int | None = None) -> None:
        self.reason_code = reason_code or self.code
        super().__init__(http_status=http_status)


class RetryableServiceIntegrationError(ServiceIntegrationError):
    code = payment_processor.constants.errors.RETRYABLE_SERVICE_INTEGRATION_ERROR_CODE
    retryable = True


class PermanentServiceIntegrationError(ServiceIntegrationError):
    code = payment_processor.constants.errors.PERMANENT_SERVICE_INTEGRATION_ERROR_CODE
