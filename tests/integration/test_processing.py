import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

import payment_processor.constants.payments
from payment_processor.apps.core.errors import (
    BrokerPublishError,
    DataAccessError,
    DataWriteConflictError,
    RetryableIntegrationError,
)
from payment_processor.apps.core.services.errors import ServiceUnavailableError
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.outbox.dao.outbox_message_dao import OutboxMessageDAO
from payment_processor.apps.outbox.models import OutboxMessage
from payment_processor.apps.outbox.services.publish_outbox_batch_service import PublishOutboxBatchService
from payment_processor.apps.payments.contracts.mappers import PaymentContractMapper
from payment_processor.apps.payments.dao.payment_dao import PaymentDAO
from payment_processor.apps.payments.dtos.payment_dto import CreatePaymentDTO, GatewayResultDTO, ProcessingEventDTO
from payment_processor.apps.payments.dtos.webhook_destination_policy_dto import WebhookDestinationPolicyDTO
from payment_processor.apps.payments.errors.base import (
    IdempotencyConflictError,
    LeaseBusyError,
    PaymentNotFoundError,
    WebhookPermanentError,
    WebhookRetryableError,
)
from payment_processor.apps.payments.models import Payment
from payment_processor.apps.payments.services.create_payment_service import CreatePaymentService
from payment_processor.apps.payments.services.get_payment_service import GetPaymentService
from payment_processor.apps.payments.services.process_payment_service import ProcessPaymentService
from payment_processor.apps.payments.services.schedule_payment_retry_service import SchedulePaymentRetryService
from payment_processor.apps.payments.services.send_payment_webhook_service import SendPaymentWebhookService

pytestmark = pytest.mark.integration
CONTRACTS = PaymentContractMapper()


def command() -> CreatePaymentDTO:
    return CreatePaymentDTO(
        Decimal('42.00'),
        payment_processor.constants.payments.Currency.RUB,
        'Test',
        {},
        'https://example.com/',
        str(uuid4()),
    )


def creator(factory):
    return CreatePaymentService(factory, CONTRACTS, WebhookDestinationPolicyDTO(frozenset({'example.com'})))


class Gateway:
    def __init__(self, status=payment_processor.constants.payments.PaymentStatus.SUCCEEDED):
        self.calls = 0
        self.status = status

    async def process(self, payment_id, amount, currency):
        self.calls += 1
        return GatewayResultDTO(
            self.status,
            'stable-reference',
            'declined' if self.status == payment_processor.constants.payments.PaymentStatus.FAILED else None,
        )


class Webhook:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = []

    async def send(self, url, event_id, payload):
        self.calls.append((event_id, payload.copy()))
        if len(self.calls) <= self.failures:
            raise WebhookRetryableError()


def processor(factory, gateway, webhook):
    return ProcessPaymentService(
        factory,
        gateway,
        CONTRACTS,
        SendPaymentWebhookService(factory, webhook),
        SchedulePaymentRetryService(factory, CONTRACTS, 2),
        30,
    )


async def next_event(factory, payment_id):
    async with factory() as uow:
        payment = await uow.payments.get_payment_by_id(payment_id)
    return ProcessingEventDTO(payment.expected_event_id, payment.id, payment.processing_attempt, utcnow())


async def make_due(engine, payment_id):
    async with engine.begin() as connection:
        await connection.execute(
            update(Payment)
            .where(Payment.id == payment_id)
            .values(next_attempt_at=utcnow() - timedelta(seconds=1), lease_expires_at=utcnow() - timedelta(seconds=1))
        )


async def test_concurrent_posts_create_one_payment_and_one_event(database):
    engine, factory = database
    create = creator(factory)
    request = command()
    payments = await asyncio.gather(*(create.execute(request) for _ in range(12)))
    assert len({payment.id for payment in payments}) == 1
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Payment)) == 1
        assert await connection.scalar(select(func.count()).select_from(OutboxMessage)) == 1
    with pytest.raises(IdempotencyConflictError):
        await create.execute(replace(request, amount=Decimal('43.00')))


async def test_outbox_failure_rolls_back_payment(database):
    engine, factory = database

    class BrokenContracts(PaymentContractMapper):
        def encode_processing(self, event):
            raise RuntimeError('Simulated failure after Payment INSERT')

    create = CreatePaymentService(factory, BrokenContracts(), WebhookDestinationPolicyDTO(frozenset({'example.com'})))
    with pytest.raises(RuntimeError):
        await create.execute(command())
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(Payment)) == 0


@pytest.mark.parametrize(
    'status',
    [
        payment_processor.constants.payments.PaymentStatus.SUCCEEDED,
        payment_processor.constants.payments.PaymentStatus.FAILED,
    ],
)
async def test_duplicate_event_does_not_repeat_gateway_or_webhook(database, status):
    _, factory = database
    payment = await creator(factory).execute(command())
    event = await next_event(factory, payment.id)
    gateway, webhook = Gateway(status), Webhook()
    service = processor(factory, gateway, webhook)
    await service.execute(event)
    await service.execute(event)
    assert gateway.calls == len(webhook.calls) == 1
    async with factory() as uow:
        result = await uow.payments.get_payment_by_id(payment.id)
    assert result.status == status
    assert result.webhook_status == payment_processor.constants.payments.WebhookStatus.DELIVERED


async def test_three_webhook_failures_persist_backoff_and_dlq(database):
    engine, factory = database
    payment = await creator(factory).execute(command())
    gateway, webhook = Gateway(), Webhook(3)
    service = processor(factory, gateway, webhook)
    original = await next_event(factory, payment.id)
    for attempt in (1, 2, 3):
        event = await next_event(factory, payment.id)
        before = utcnow()
        await service.execute(event)
        async with factory() as uow:
            current = await uow.payments.get_payment_by_id(payment.id)
        assert current.status == payment_processor.constants.payments.PaymentStatus.SUCCEEDED
        if attempt < 3:
            assert current.processing_attempt == attempt + 1
            assert (current.next_attempt_at - before).total_seconds() >= 2**attempt - 0.1
            await service.execute(original)
            assert len(webhook.calls) == attempt
            await make_due(engine, payment.id)
    assert gateway.calls == 1
    assert len(webhook.calls) == 3
    assert len({str(event_id) for event_id, _ in webhook.calls}) == 1
    assert webhook.calls[0][1] == webhook.calls[2][1]
    assert current.webhook_status == payment_processor.constants.payments.WebhookStatus.EXHAUSTED
    async with engine.connect() as connection:
        assert (
            await connection.scalar(
                select(func.count())
                .select_from(OutboxMessage)
                .where(OutboxMessage.event_type == 'payment.processing.exhausted')
            )
            == 1
        )
    await service.execute(await next_event(factory, payment.id))
    assert len(webhook.calls) == 3


class SimulatedCrash(BaseException):
    pass


async def test_restart_after_terminal_status_does_not_charge_again(database):
    engine, factory = database
    payment = await creator(factory).execute(command())
    gateway = Gateway()

    class CrashOnceWebhook(Webhook):
        async def send(self, url, event_id, payload):
            if not self.calls:
                self.calls.append((event_id, payload.copy()))
                raise SimulatedCrash()
            await super().send(url, event_id, payload)

    webhook = CrashOnceWebhook()
    service = processor(factory, gateway, webhook)
    event = await next_event(factory, payment.id)
    with pytest.raises(SimulatedCrash):
        await service.execute(event)
    await make_due(engine, payment.id)
    await service.execute(event)
    assert gateway.calls == 1
    assert len(webhook.calls) == 2
    assert webhook.calls[0] == webhook.calls[1]


async def test_no_db_connection_held_during_gateway_and_concurrent_claim_is_fenced(database):
    engine, factory = database
    payment = await creator(factory).execute(command())
    started, release = asyncio.Event(), asyncio.Event()

    class SlowGateway(Gateway):
        async def process(self, *args):
            started.set()
            await release.wait()
            return await super().process(*args)

    gateway, webhook = SlowGateway(), Webhook()
    service = processor(factory, gateway, webhook)
    event = await next_event(factory, payment.id)
    task = asyncio.create_task(service.execute(event))
    await asyncio.wait_for(started.wait(), timeout=5)
    try:
        assert engine.pool.checkedout() == 0
        with pytest.raises(LeaseBusyError):
            await service.execute(event)
    finally:
        release.set()
        await task
    assert gateway.calls == 1


class Publisher:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    async def publish(self, message):
        self.messages.append(message)
        if self.fail:
            raise BrokerPublishError()


async def test_parallel_dispatchers_claim_disjoint_batches(database):
    _, factory = database
    await asyncio.gather(*(creator(factory).execute(command()) for _ in range(20)))
    publisher = Publisher()
    service = PublishOutboxBatchService(factory, publisher, 10, 4, 30)
    counts = await asyncio.gather(service.execute(), service.execute())
    assert sum(counts) == 20
    assert len({message.id for message in publisher.messages}) == 20


async def test_unconfirmed_publication_stays_in_outbox(database):
    engine, factory = database
    await creator(factory).execute(command())
    publisher = Publisher(fail=True)
    assert await PublishOutboxBatchService(factory, publisher, 10, 4, 30).execute() == 0
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                select(OutboxMessage.published_at, OutboxMessage.last_error, OutboxMessage.available_at)
            )
        ).one()
    assert row.published_at is None
    assert row.last_error == 'broker_publish_failed'
    assert row.available_at > utcnow()


async def test_crash_after_publish_replays_stable_message_id(database, monkeypatch):
    engine, factory = database
    await creator(factory).execute(command())
    publisher = Publisher()
    service = PublishOutboxBatchService(factory, publisher, 10, 4, 30)
    original = OutboxMessageDAO.mark_outbox_message_published

    async def fail_mark(*args, **kwargs):
        raise DataAccessError()

    monkeypatch.setattr(OutboxMessageDAO, 'mark_outbox_message_published', fail_mark)
    assert await service.execute() == 0
    monkeypatch.setattr(OutboxMessageDAO, 'mark_outbox_message_published', original)
    async with engine.begin() as connection:
        await connection.execute(update(OutboxMessage).values(lease_expires_at=utcnow() - timedelta(seconds=1)))
    assert await service.execute() == 1
    assert publisher.messages[0].id == publisher.messages[1].id


async def test_expired_lease_owner_cannot_overwrite_new_owner(database):
    engine, factory = database
    payment = await creator(factory).execute(command())
    event = await next_event(factory, payment.id)
    old_token, new_token = uuid4(), uuid4()
    async with factory() as uow:
        assert await uow.payments.claim_payment_for_processing_exclusive(event, old_token, 30) is not None
    await make_due(engine, payment.id)
    async with factory() as uow:
        assert await uow.payments.claim_payment_for_processing_exclusive(event, new_token, 30) is not None
    with pytest.raises(DataWriteConflictError):
        async with factory() as uow:
            await uow.payments.mark_payment_webhook_delivered(payment.id, old_token)


async def test_unknown_gateway_outcome_remains_pending_after_retry_budget(database):
    engine, factory = database
    payment = await creator(factory).execute(command())

    class UnavailableGateway(Gateway):
        async def process(self, *args):
            self.calls += 1
            raise RetryableIntegrationError()

    gateway, webhook = UnavailableGateway(), Webhook()
    service = processor(factory, gateway, webhook)
    for _ in range(3):
        await service.execute(await next_event(factory, payment.id))
        await make_due(engine, payment.id)
    async with factory() as uow:
        current = await uow.payments.get_payment_by_id(payment.id)
    assert current.status == payment_processor.constants.payments.PaymentStatus.PENDING
    assert current.processing_exhausted_at is not None
    assert current.webhook_status == payment_processor.constants.payments.WebhookStatus.NOT_READY
    assert gateway.calls == 3
    assert not webhook.calls


async def test_permanent_webhook_error_dead_letters_without_changing_payment_result(database):
    _, factory = database
    payment = await creator(factory).execute(command())

    class RejectedWebhook(Webhook):
        async def send(self, *args):
            raise WebhookPermanentError(http_status=400)

    await processor(factory, Gateway(), RejectedWebhook()).execute(await next_event(factory, payment.id))
    async with factory() as uow:
        current = await uow.payments.get_payment_by_id(payment.id)
    assert current.status == payment_processor.constants.payments.PaymentStatus.SUCCEEDED
    assert current.webhook_attempts == 1
    assert current.webhook_status == payment_processor.constants.payments.WebhookStatus.EXHAUSTED


async def test_get_payment__missing_record__raises_service_error_with_dao_cause(database):
    _, factory = database

    with pytest.raises(PaymentNotFoundError) as caught:
        await GetPaymentService(factory).execute(uuid4())

    assert isinstance(caught.value.__cause__, PaymentDAO.PaymentDoesNotExistException)


async def test_process_payment__result_write_fails__does_not_schedule_integration_retry(database, monkeypatch):
    engine, factory = database
    payment = await creator(factory).execute(command())
    event = await next_event(factory, payment.id)
    gateway, webhook = Gateway(), Webhook()
    failure = DataAccessError()

    async def fail_write(*args, **kwargs):
        raise failure

    monkeypatch.setattr(PaymentDAO, 'update_payment_gateway_result', fail_write)

    with pytest.raises(ServiceUnavailableError) as caught:
        await processor(factory, gateway, webhook).execute(event)

    assert caught.value.__cause__ is failure
    assert gateway.calls == 1
    assert not webhook.calls
    async with factory() as uow:
        current = await uow.payments.get_payment_by_id(payment.id)
    assert current.processing_attempt == 1
    assert current.expected_event_id == event.event_id
    assert current.status == payment_processor.constants.payments.PaymentStatus.PENDING
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(OutboxMessage)) == 1
