from typing import Final

SETTINGS_DATABASE_POOL_MAX_SIZE: Final = 100
SETTINGS_DATABASE_STATEMENT_TIMEOUT_MIN_MS: Final = 100
SETTINGS_CONCURRENCY_MAX: Final = 64
SETTINGS_OUTBOX_BATCH_MAX_SIZE: Final = 1000
SETTINGS_LEASE_MIN_SECONDS: Final = 10
SETTINGS_LEASE_DEADLINE_MARGIN_SECONDS: Final = 5
SETTINGS_REQUEST_BODY_MIN_BYTES: Final = 1024
SETTINGS_REQUEST_BODY_MAX_BYTES: Final = 1048576

SETTINGS_WEBHOOK_PRIVATE_PRODUCTION_REJECTED_MESSAGE = 'Private webhook destinations are only permitted in development'
SETTINGS_WEBHOOK_PRIVATE_HOST_NOT_ALLOWED_MESSAGE = 'Private webhook hosts must also be explicitly allowed'
SETTINGS_GATEWAY_DELAY_ORDER_INVALID_MESSAGE = 'Gateway delay maximum must be at least its minimum'
SETTINGS_GATEWAY_PRODUCTION_DELAY_INVALID_MESSAGE = 'Production simulator must use the required 2-5 second delay'
SETTINGS_PROCESSING_LEASE_TOO_SHORT_MESSAGE = 'Processing lease must exceed external operation deadlines'
SETTINGS_OUTBOX_LEASE_TOO_SHORT_MESSAGE = 'Outbox lease is too short for the configured batch'
