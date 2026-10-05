from typing import Final

HTTP_HEADER_API_KEY: Final = 'X-API-Key'
HTTP_HEADER_REQUEST_ID: Final = 'X-Request-Id'
HTTP_HEADER_IDEMPOTENCY_KEY: Final = 'Idempotency-Key'
HTTP_HEADER_CONTENT_TYPE: Final = 'Content-Type'
HTTP_HEADER_ENCODING: Final = 'latin-1'
HTTP_WSGI_API_KEY_ENVIRON_NAME: Final = 'HTTP_X_API_KEY'
HTTP_MEDIA_TYPE_JSON: Final = 'application/json'
HTTP_API_KEY_MIN_LENGTH: Final = 24
HTTP_SERVER_BIND_HOST: Final = '0.0.0.0'
HTTP_API_SERVER_PORT: Final = 8000

HTTP_ERROR_VALIDATION_CODE = 'validation_error'
HTTP_ERROR_VALIDATION_MESSAGE = 'Request data is invalid.'
HTTP_ERROR_REQUEST_CODE = 'http_error'
HTTP_ERROR_REQUEST_MESSAGE = 'Request could not be served.'
HTTP_ERROR_INTERNAL_CODE = 'internal_error'
HTTP_ERROR_INTERNAL_MESSAGE = 'An unexpected error occurred.'
HTTP_ERROR_AUTHENTICATION_CODE = 'authentication_failed'
HTTP_ERROR_AUTHENTICATION_MESSAGE = 'API key is missing or invalid.'
HTTP_ERROR_BODY_TOO_LARGE_CODE = 'request_too_large'
HTTP_ERROR_BODY_TOO_LARGE_MESSAGE = 'Request body is too large.'
