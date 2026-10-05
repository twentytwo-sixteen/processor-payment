from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from payment_processor.api import create_app
from payment_processor.apps.core.services.errors import ServiceUnavailableError
from payment_processor.apps.payments.errors.base import IdempotencyConflictError, PaymentNotFoundError
from payment_processor.settings.application import ApplicationSettings

KEY = 'local-development-api-key-change-me'


@pytest.fixture
async def client():
    settings = ApplicationSettings(
        api_key=KEY,
        database_url='postgresql+asyncpg://x:x@localhost/x',
        rabbitmq_url='amqp://localhost',
        _env_file=None,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test'
    ) as client:
        yield client, app.state.runtime
    await app.state.runtime.close()


@pytest.mark.parametrize('path', ['/api/v1/payments/x', '/docs', '/openapi.json', '/metrics', '/health/ready'])
async def test_all_http_endpoints_require_authentication(client, path):
    http, _ = client
    response = await http.get(path)
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'authentication_failed'
    assert response.headers['x-request-id']


@pytest.mark.parametrize(('error', 'status'), [(PaymentNotFoundError(), 404), (ServiceUnavailableError(), 503)])
async def test_service_error_mapping(client, error, status):
    http, runtime = client
    runtime.get_payment = AsyncMock()
    runtime.get_payment.execute.side_effect = error
    response = await http.get(f'/api/v1/payments/{uuid4()}', headers={'X-API-Key': KEY})
    assert response.status_code == status
    assert response.json()['error']['code'] == error.code


async def test_conflict_and_validation_do_not_echo_secrets(client):
    http, runtime = client
    runtime.create_payment = AsyncMock()
    runtime.create_payment.execute.side_effect = IdempotencyConflictError()
    headers = {'X-API-Key': KEY, 'Idempotency-Key': 'key'}
    body = {'amount': '1.00', 'currency': 'RUB', 'webhook_url': 'https://example.com/'}
    response = await http.post('/api/v1/payments', headers=headers, json=body)
    assert response.status_code == 409
    response = await http.post('/api/v1/payments', headers=headers, json=body | {'amount': 'SECRET-PAYLOAD'})
    assert response.status_code == 422
    assert 'SECRET-PAYLOAD' not in response.text


async def test_oversized_body_rejected_before_service(client):
    http, runtime = client
    runtime.create_payment = AsyncMock()
    response = await http.post('/api/v1/payments', headers={'X-API-Key': KEY}, content=b'x' * 65537)
    assert response.status_code == 413
    runtime.create_payment.execute.assert_not_called()


async def test_unexpected_error_is_safe_and_has_correlation_id(client):
    http, runtime = client
    runtime.get_payment = AsyncMock()
    runtime.get_payment.execute.side_effect = RuntimeError('SECRET-INTERNAL-DETAIL')
    response = await http.get(f'/api/v1/payments/{uuid4()}', headers={'X-API-Key': KEY})
    assert response.status_code == 500
    assert 'SECRET-INTERNAL-DETAIL' not in response.text
    assert response.headers['x-request-id'] == response.json()['error']['request_id']
