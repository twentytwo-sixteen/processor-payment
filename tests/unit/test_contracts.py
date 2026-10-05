from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

import payment_processor.constants.payments
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.payments.contracts.processing_event import PaymentProcessingRequested
from payment_processor.apps.payments.dtos.payment_dto import CreatePaymentDTO
from payment_processor.apps.payments.dtos.webhook_destination_policy_dto import WebhookDestinationPolicyDTO
from payment_processor.apps.payments.errors.base import (
    PaymentRuleViolationError,
    WebhookDestinationError,
    WebhookPermanentError,
)
from payment_processor.apps.payments.infrastructure.clients.simulated_gateway import SimulatedGateway
from payment_processor.apps.payments.infrastructure.clients.webhook_client import ValidatedResolver
from payment_processor.apps.payments.services.create_payment_service import CreatePaymentService
from payment_processor.apps.payments.specifications.payment_specification import PaymentSpecification
from payment_processor.apps.payments.specifications.webhook_destination_specification import (
    WebhookDestinationSpecification,
)
from payment_processor.apps.rest_api.v1.payments.payment_schemas import CreatePaymentRequest
from payment_processor.settings.application import ApplicationSettings


def command() -> CreatePaymentDTO:
    return CreatePaymentDTO(
        Decimal('10.00'),
        payment_processor.constants.payments.Currency.RUB,
        '',
        {'b': 2, 'a': 1},
        'https://example.com/',
        'key',
    )


@pytest.mark.parametrize('amount', ['0', '-1', '0.001', 'NaN', 'Infinity', '10000000000000000'])
def test_invalid_money_is_rejected(amount: str) -> None:
    with pytest.raises(PaymentRuleViolationError):
        PaymentSpecification.affirm(replace(command(), amount=Decimal(amount)))


def test_fingerprint_ignores_decimal_scale_and_json_key_order() -> None:
    other = replace(command(), amount=Decimal('10'), metadata={'a': 1, 'b': 2})
    assert CreatePaymentService._request_fingerprint(command()) == CreatePaymentService._request_fingerprint(other)
    assert CreatePaymentService._request_fingerprint(command()) != CreatePaymentService._request_fingerprint(
        replace(command(), webhook_url='https://example.com/x')
    )


@pytest.mark.parametrize(
    'url',
    [
        'http://example.com/',
        'https://evil.com/',
        'https://a:b@example.com/',
        'https://example.com/#fragment',
        'https://127.0.0.1/',
    ],
)
def test_unsafe_destinations_are_rejected(url: str) -> None:
    with pytest.raises(WebhookDestinationError):
        WebhookDestinationSpecification.affirm(
            url, WebhookDestinationPolicyDTO(frozenset({'example.com', '127.0.0.1'}))
        )


def test_http_money_requires_string() -> None:
    with pytest.raises(ValidationError):
        CreatePaymentRequest(amount=1.1, currency='RUB', webhook_url='https://example.com/')


def test_event_rejects_unknown_version_and_naive_datetime() -> None:
    values = {'event_id': uuid4(), 'payment_id': uuid4(), 'attempt': 1, 'occurred_at': utcnow()}
    with pytest.raises(ValidationError):
        PaymentProcessingRequested(**values, schema_version=2)
    with pytest.raises(ValidationError):
        PaymentProcessingRequested(**(values | {'occurred_at': utcnow().replace(tzinfo=None)}))


async def test_simulator_replays_same_result() -> None:
    gateway = SimulatedGateway(0, 0)
    payment_id = uuid4()
    first = await gateway.process(payment_id, Decimal('10'), 'RUB')
    assert first == await gateway.process(payment_id, Decimal('10'), 'RUB')


def test_production_disallows_private_webhooks() -> None:
    with pytest.raises(ValidationError):
        ApplicationSettings(
            environment='production',
            api_key='x' * 24,
            database_url='postgresql://x',
            rabbitmq_url='amqp://x',
            webhook_allowed_hosts=['localhost'],
            webhook_private_hosts=['localhost'],
            _env_file=None,
        )


async def test_dns_resolution_rejects_private_actual_connection_address(monkeypatch):
    from unittest.mock import AsyncMock

    resolver = ValidatedResolver(WebhookDestinationPolicyDTO(frozenset({'example.com'})))
    monkeypatch.setattr(resolver._resolver, 'resolve', AsyncMock(return_value=[{'host': '127.0.0.1'}]))
    try:
        with pytest.raises(WebhookPermanentError):
            await resolver.resolve('example.com', 443)
    finally:
        await resolver.close()
