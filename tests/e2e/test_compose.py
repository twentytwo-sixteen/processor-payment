import asyncio
import json
import os
import subprocess
import time
from uuid import uuid4

import aio_pika
import httpx
import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture
async def http():
    url = os.getenv('E2E_API_URL')
    if not url:
        pytest.skip('Set E2E_API_URL to the running Compose API')
    async with httpx.AsyncClient(base_url=url, headers={'X-API-Key': os.environ['E2E_API_KEY']}, timeout=5) as client:
        yield client


async def create(http, path='/success', key=None):
    response = await http.post(
        '/api/v1/payments',
        headers={'Idempotency-Key': key or str(uuid4())},
        json={
            'amount': '123.45',
            'currency': 'RUB',
            'description': 'E2E',
            'metadata': {'test': True},
            'webhook_url': f'http://webhook-receiver:8080{path}',
        },
    )
    assert response.status_code == 202, response.text
    return response.json()['payment_id']


async def wait_for(http, payment_id, predicate, deadline_seconds=35):
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        response = await http.get(f'/api/v1/payments/{payment_id}')
        assert response.status_code == 200, response.text
        payment = response.json()
        if predicate(payment):
            return payment
        await asyncio.sleep(0.2)
    pytest.fail(f'Payment {payment_id} did not reach the expected state')


async def compose(*args):
    result = await asyncio.to_thread(
        subprocess.run,
        ['docker', 'compose', *args],
        cwd=os.getenv('E2E_COMPOSE_DIR'),
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stderr


async def test_real_concurrent_post_and_webhook(http):
    key = str(uuid4())
    payments = await asyncio.gather(*(create(http, key=key) for _ in range(10)))
    assert len(set(payments)) == 1
    result = await wait_for(http, payments[0], lambda value: value['webhook_status'] == 'delivered')
    assert result['status'] in ('succeeded', 'failed')
    assert result['amount'] == '123.45'
    assert result['webhook_attempts'] == 1


async def test_retry_schedule_survives_consumer_restart(http):
    payment_id = await create(http, '/fail-twice')
    before = await wait_for(
        http, payment_id, lambda value: value['webhook_attempts'] == 1 and value['webhook_last_error']
    )
    await compose('restart', 'consumer')
    after = await wait_for(http, payment_id, lambda value: value['webhook_status'] == 'delivered')
    assert after['webhook_attempts'] == 3
    assert before['status'] == after['status']
    assert before['processed_at'] == after['processed_at']


async def test_failed_webhook_reaches_real_dlq_after_three_attempts(http):
    payment_id = await create(http, '/always-fail')
    result = await wait_for(http, payment_id, lambda value: value['webhook_status'] == 'exhausted')
    assert result['webhook_attempts'] == 3
    assert result['status'] in ('succeeded', 'failed')
    connection = await aio_pika.connect_robust(os.environ['E2E_RABBITMQ_URL'])
    pending = []
    try:
        channel = await connection.channel()
        queue = await channel.get_queue('payments.dlq')
        deadline = time.monotonic() + 10
        found = None
        while time.monotonic() < deadline:
            message = await queue.get(fail=False)
            if message is None:
                await asyncio.sleep(0.2)
                continue
            value = json.loads(message.body)
            if value.get('payment_id') == payment_id:
                found = value
                await message.ack()
                break
            pending.append(message)
        assert found is not None
        assert found['attempt'] == 3
        assert found['stage'] == 'webhook'
        assert found['error_code'] == 'webhook_temporarily_unavailable'
    finally:
        for message in pending:
            await message.nack(requeue=True)
        await connection.close()


async def test_broker_outage_keeps_api_available_and_outbox_recovers(http):
    await compose('stop', 'rabbitmq')
    try:
        assert (await http.get('/health/ready')).status_code == 200
        payment_id = await create(http)
        result = await http.get(f'/api/v1/payments/{payment_id}')
        assert result.json()['status'] == 'pending'
    finally:
        await compose('start', 'rabbitmq')
    await wait_for(http, payment_id, lambda value: value['webhook_status'] == 'delivered', deadline_seconds=45)


async def test_database_outage_maps_to_503_and_recovers(http):
    await compose('stop', 'postgres')
    try:
        response = await http.get('/health/ready')
        assert response.status_code == 503, response.text
        assert response.json()['error']['code'] == 'service_unavailable'
    finally:
        await compose('start', 'postgres')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (await http.get('/health/ready')).status_code == 200:
            return
        await asyncio.sleep(0.5)
    pytest.fail('Database readiness did not recover')


async def test_worker_metrics_require_api_key(http):
    url = os.getenv('E2E_METRICS_URL', 'http://127.0.0.1:19001/metrics')
    async with httpx.AsyncClient(timeout=2) as client:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                response = await client.get(url)
            except httpx.TransportError:
                await asyncio.sleep(0.5)
                continue
            break
        else:
            pytest.fail('Worker metrics did not recover after the database outage')
        assert response.status_code == 401
        response = await client.get(url, headers={'X-API-Key': os.environ['E2E_API_KEY']})
        assert response.status_code == 200
        assert 'payment_outbox_pending' in response.text


async def test_malformed_message_is_dead_lettered_by_broker(http):
    connection = await aio_pika.connect_robust(os.environ['E2E_RABBITMQ_URL'])
    pending = []
    message_id = str(uuid4())
    try:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange = await channel.get_exchange('payments.events')
        await exchange.publish(
            aio_pika.Message(
                body=b'{malformed', message_id=message_id, content_type='application/json', delivery_mode=2
            ),
            routing_key='payments.new',
            mandatory=True,
        )
        queue = await channel.get_queue('payments.dlq')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            message = await queue.get(fail=False)
            if message is None:
                await asyncio.sleep(0.2)
                continue
            if message.message_id == message_id:
                assert message.headers['x-death'][0]['reason'] == 'rejected'
                await message.ack()
                return
            pending.append(message)
        pytest.fail('Malformed message was not transferred through the configured DLX')
    finally:
        for message in pending:
            await message.nack(requeue=True)
        await connection.close()
