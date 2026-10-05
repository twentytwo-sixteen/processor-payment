import payment_processor.constants.payment_errors
from payment_processor.apps.core.errors import ApplicationError, PermanentIntegrationError, RetryableIntegrationError
from payment_processor.apps.core.services.errors import (
    PermanentServiceIntegrationError,
    ServiceConflictError,
    ServiceNotFoundError,
    ServiceValidationError,
)


class PaymentValidationError(ServiceValidationError):
    code = payment_processor.constants.payment_errors.PAYMENT_VALIDATION_ERROR_CODE
    message = payment_processor.constants.payment_errors.PAYMENT_VALIDATION_ERROR_MESSAGE


class PaymentNotFoundError(ServiceNotFoundError):
    code = payment_processor.constants.payment_errors.PAYMENT_NOT_FOUND_ERROR_CODE
    message = payment_processor.constants.payment_errors.PAYMENT_NOT_FOUND_ERROR_MESSAGE


class IdempotencyConflictError(ServiceConflictError):
    code = payment_processor.constants.payment_errors.IDEMPOTENCY_CONFLICT_ERROR_CODE
    message = payment_processor.constants.payment_errors.IDEMPOTENCY_CONFLICT_ERROR_MESSAGE


class LeaseBusyError(ServiceConflictError):
    code = payment_processor.constants.payment_errors.LEASE_BUSY_ERROR_CODE
    message = payment_processor.constants.payment_errors.LEASE_BUSY_ERROR_MESSAGE


class LeaseLostError(ServiceConflictError):
    code = payment_processor.constants.payment_errors.LEASE_LOST_ERROR_CODE
    message = payment_processor.constants.payment_errors.LEASE_LOST_ERROR_MESSAGE


class WebhookURLRejectedError(PaymentValidationError):
    code = payment_processor.constants.payment_errors.WEBHOOK_URL_REJECTED_ERROR_CODE
    message = payment_processor.constants.payment_errors.WEBHOOK_URL_REJECTED_ERROR_MESSAGE


class PaymentRuleViolationError(ApplicationError):
    code = payment_processor.constants.payment_errors.PAYMENT_RULE_VIOLATION_ERROR_CODE
    message = payment_processor.constants.payment_errors.PAYMENT_RULE_VIOLATION_ERROR_MESSAGE


class WebhookDestinationError(PaymentRuleViolationError):
    code = payment_processor.constants.payment_errors.WEBHOOK_DESTINATION_ERROR_CODE
    message = payment_processor.constants.payment_errors.WEBHOOK_DESTINATION_ERROR_MESSAGE


class WebhookRetryableError(RetryableIntegrationError):
    code = payment_processor.constants.payment_errors.WEBHOOK_RETRYABLE_ERROR_CODE


class WebhookPermanentError(PermanentIntegrationError):
    code = payment_processor.constants.payment_errors.WEBHOOK_PERMANENT_ERROR_CODE


class WebhookAttemptsExhaustedError(PermanentServiceIntegrationError):
    code = payment_processor.constants.payment_errors.WEBHOOK_ATTEMPTS_EXHAUSTED_ERROR_CODE
