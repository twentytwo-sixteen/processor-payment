from math import ceil
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import payment_processor.constants.http
import payment_processor.constants.payments
import payment_processor.constants.settings


class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', hide_input_in_errors=True)

    environment: Literal['development', 'production'] = 'production'
    api_key: SecretStr = Field(min_length=payment_processor.constants.http.HTTP_API_KEY_MIN_LENGTH)
    database_url: SecretStr
    rabbitmq_url: SecretStr
    webhook_allowed_hosts: list[str] = Field(default_factory=list)
    webhook_private_hosts: list[str] = Field(default_factory=list)
    database_pool_size: int = Field(
        default=10, ge=1, le=payment_processor.constants.settings.SETTINGS_DATABASE_POOL_MAX_SIZE
    )
    database_max_overflow: int = Field(
        default=10,
        ge=0,
        le=payment_processor.constants.settings.SETTINGS_DATABASE_POOL_MAX_SIZE,
    )
    database_statement_timeout_ms: int = Field(
        default=5000,
        ge=payment_processor.constants.settings.SETTINGS_DATABASE_STATEMENT_TIMEOUT_MIN_MS,
    )
    database_pool_timeout_seconds: float = Field(default=5.0, gt=0)
    database_lock_timeout_ms: int = Field(default=5000, ge=1)
    consumer_concurrency: int = Field(default=8, ge=1, le=payment_processor.constants.settings.SETTINGS_CONCURRENCY_MAX)
    outbox_batch_size: int = Field(
        default=32, ge=1, le=payment_processor.constants.settings.SETTINGS_OUTBOX_BATCH_MAX_SIZE
    )
    publisher_concurrency: int = Field(
        default=8, ge=1, le=payment_processor.constants.settings.SETTINGS_CONCURRENCY_MAX
    )
    outbox_poll_interval: float = Field(default=0.25, gt=0)
    publisher_timeout: float = Field(default=3.0, gt=0)
    processing_lease_seconds: int = Field(
        default=30, ge=payment_processor.constants.settings.SETTINGS_LEASE_MIN_SECONDS
    )
    outbox_lease_seconds: int = Field(default=30, ge=payment_processor.constants.settings.SETTINGS_LEASE_MIN_SECONDS)
    webhook_timeout: float = Field(default=5.0, gt=0)
    webhook_connect_timeout_seconds: float = Field(default=2.0, gt=0)
    gateway_delay_min: float = Field(
        default=payment_processor.constants.payments.PAYMENT_GATEWAY_DELAY_MIN_SECONDS, ge=0
    )
    gateway_delay_max: float = Field(
        default=payment_processor.constants.payments.PAYMENT_GATEWAY_DELAY_MAX_SECONDS, ge=0
    )
    retry_base_seconds: float = Field(default=2.0, gt=0)
    max_request_bytes: int = Field(
        default=65536,
        ge=payment_processor.constants.settings.SETTINGS_REQUEST_BODY_MIN_BYTES,
        le=payment_processor.constants.settings.SETTINGS_REQUEST_BODY_MAX_BYTES,
    )

    @model_validator(mode='after')
    def validate_runtime_limits(self) -> Self:
        self._validate_webhook_hosts()
        self._validate_gateway_delays()
        self._validate_leases()
        return self

    def _validate_webhook_hosts(self) -> None:
        if self.webhook_private_hosts and self.environment != 'development':
            raise ValueError(payment_processor.constants.settings.SETTINGS_WEBHOOK_PRIVATE_PRODUCTION_REJECTED_MESSAGE)
        if not set(self.webhook_private_hosts).issubset(self.webhook_allowed_hosts):
            raise ValueError(payment_processor.constants.settings.SETTINGS_WEBHOOK_PRIVATE_HOST_NOT_ALLOWED_MESSAGE)

    def _validate_gateway_delays(self) -> None:
        if self.gateway_delay_max < self.gateway_delay_min:
            raise ValueError(payment_processor.constants.settings.SETTINGS_GATEWAY_DELAY_ORDER_INVALID_MESSAGE)
        if self.environment == 'production' and (
            self.gateway_delay_min != payment_processor.constants.payments.PAYMENT_GATEWAY_DELAY_MIN_SECONDS
            or self.gateway_delay_max != payment_processor.constants.payments.PAYMENT_GATEWAY_DELAY_MAX_SECONDS
        ):
            raise ValueError(payment_processor.constants.settings.SETTINGS_GATEWAY_PRODUCTION_DELAY_INVALID_MESSAGE)

    def _validate_leases(self) -> None:
        if self.processing_lease_seconds <= (
            self.gateway_delay_max
            + self.webhook_timeout
            + payment_processor.constants.settings.SETTINGS_LEASE_DEADLINE_MARGIN_SECONDS
        ):
            raise ValueError(payment_processor.constants.settings.SETTINGS_PROCESSING_LEASE_TOO_SHORT_MESSAGE)
        waves = ceil(self.outbox_batch_size / self.publisher_concurrency)
        if self.outbox_lease_seconds <= (
            waves * self.publisher_timeout + payment_processor.constants.settings.SETTINGS_LEASE_DEADLINE_MARGIN_SECONDS
        ):
            raise ValueError(payment_processor.constants.settings.SETTINGS_OUTBOX_LEASE_TOO_SHORT_MESSAGE)
