from typing import ClassVar

import payment_processor.constants.errors


class ApplicationError(Exception):
    code: ClassVar[str] = payment_processor.constants.errors.APPLICATION_ERROR_CODE
    message: ClassVar[str] = payment_processor.constants.errors.APPLICATION_ERROR_MESSAGE

    def __init__(self, *, http_status: int | None = None) -> None:
        self.http_status = http_status
        super().__init__(self.message)


class DataAccessError(ApplicationError):
    code = payment_processor.constants.errors.DATA_ACCESS_ERROR_CODE
    message = payment_processor.constants.errors.DATA_ACCESS_ERROR_MESSAGE


class DataIntegrityError(ApplicationError):
    code = payment_processor.constants.errors.DATA_INTEGRITY_ERROR_CODE
    message = payment_processor.constants.errors.DATA_INTEGRITY_ERROR_MESSAGE


class DataNotFoundError(ApplicationError):
    code = payment_processor.constants.errors.DATA_NOT_FOUND_ERROR_CODE
    message = payment_processor.constants.errors.DATA_NOT_FOUND_ERROR_MESSAGE


class DataWriteConflictError(ApplicationError):
    code = payment_processor.constants.errors.DATA_WRITE_CONFLICT_ERROR_CODE
    message = payment_processor.constants.errors.DATA_WRITE_CONFLICT_ERROR_MESSAGE


class ContractEncodingError(ApplicationError):
    code = payment_processor.constants.errors.CONTRACT_ENCODING_ERROR_CODE
    message = payment_processor.constants.errors.CONTRACT_ENCODING_ERROR_MESSAGE


class RetryableIntegrationError(ApplicationError):
    code = payment_processor.constants.errors.RETRYABLE_INTEGRATION_ERROR_CODE
    message = payment_processor.constants.errors.RETRYABLE_INTEGRATION_ERROR_MESSAGE


class PermanentIntegrationError(ApplicationError):
    code = payment_processor.constants.errors.PERMANENT_INTEGRATION_ERROR_CODE
    message = payment_processor.constants.errors.PERMANENT_INTEGRATION_ERROR_MESSAGE


class BrokerPublishError(RetryableIntegrationError):
    code = payment_processor.constants.errors.BROKER_PUBLISH_ERROR_CODE


class RequestBodyTooLargeError(ApplicationError):
    code = payment_processor.constants.errors.REQUEST_BODY_TOO_LARGE_ERROR_CODE
    message = payment_processor.constants.errors.REQUEST_BODY_TOO_LARGE_ERROR_MESSAGE
