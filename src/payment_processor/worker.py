import asyncio
import logging
import signal
import time
from contextlib import AsyncExitStack, suppress
from wsgiref.simple_server import WSGIServer

from faststream.rabbit import RabbitBroker

import payment_processor.constants.worker
from payment_processor.apps.core.messaging.rabbit_publisher import RabbitPublisher
from payment_processor.apps.core.messaging.topology import create_broker, declare_topology
from payment_processor.apps.core.metrics_server import start_authenticated_metrics
from payment_processor.apps.core.observability import OUTBOX_AGE, OUTBOX_PENDING, configure_logging
from payment_processor.apps.core.runtime import Runtime
from payment_processor.apps.core.services.errors import ServiceUnavailableError
from payment_processor.apps.core.types import utcnow
from payment_processor.apps.outbox.services.get_outbox_stats_service import GetOutboxStatsService
from payment_processor.apps.outbox.services.publish_outbox_batch_service import PublishOutboxBatchService
from payment_processor.apps.worker.handlers.payment_handler import register_payment_handler
from payment_processor.settings.application import ApplicationSettings

logger = logging.getLogger(__name__)


async def dispatch_loop(
    broker: RabbitBroker,
    publisher: PublishOutboxBatchService,
    stats_service: GetOutboxStatsService,
    stop: asyncio.Event,
    poll_interval: float,
) -> None:
    next_metrics = 0.0
    while not stop.is_set():
        if not await _publish_outbox(publisher):
            await _wait_for_stop(stop, payment_processor.constants.worker.WORKER_STORAGE_RECOVERY_DELAY_SECONDS)
            continue
        if time.monotonic() >= next_metrics:
            if not await _refresh_metrics(stats_service):
                await _wait_for_stop(stop, payment_processor.constants.worker.WORKER_STORAGE_RECOVERY_DELAY_SECONDS)
                continue
            next_metrics = time.monotonic() + payment_processor.constants.worker.WORKER_METRICS_REFRESH_INTERVAL_SECONDS
        if await broker.ping(timeout=payment_processor.constants.worker.WORKER_BROKER_PING_TIMEOUT_SECONDS):
            await asyncio.to_thread(
                payment_processor.constants.worker.WORKER_HEARTBEAT_PATH.write_text,
                str(time.time()),
            )
        await _wait_for_stop(stop, poll_interval)


async def _publish_outbox(service: PublishOutboxBatchService) -> bool:
    try:
        await service.execute()
    except ServiceUnavailableError as error:
        logger.warning('dispatcher_storage_unavailable', extra={'error_code': error.code}, exc_info=error)
        return False
    return True


async def _refresh_metrics(service: GetOutboxStatsService) -> bool:
    try:
        stats = await service.execute()
    except ServiceUnavailableError as error:
        logger.warning('outbox_metrics_unavailable', extra={'error_code': error.code}, exc_info=error)
        return False
    OUTBOX_PENDING.set(stats.pending)
    OUTBOX_AGE.set(max(0, (utcnow() - stats.oldest_created_at).total_seconds()) if stats.oldest_created_at else 0)
    return True


async def _wait_for_stop(stop: asyncio.Event, delay_seconds: float) -> None:
    with suppress(TimeoutError):
        async with asyncio.timeout(delay_seconds):
            await stop.wait()


async def _close_metrics_server(server: WSGIServer) -> None:
    await asyncio.to_thread(server.shutdown)
    await asyncio.to_thread(server.server_close)


async def main() -> None:
    settings = ApplicationSettings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    async with AsyncExitStack() as resources:
        metrics_server = start_authenticated_metrics(settings.api_key.get_secret_value())
        resources.push_async_callback(
            asyncio.to_thread,
            payment_processor.constants.worker.WORKER_HEARTBEAT_PATH.unlink,
            missing_ok=True,
        )
        resources.push_async_callback(_close_metrics_server, metrics_server)
        runtime = Runtime(settings)
        resources.push_async_callback(runtime.close)
        broker = create_broker(settings.rabbitmq_url.get_secret_value(), settings.consumer_concurrency)
        resources.push_async_callback(broker.stop)
        processor, dispatcher = await runtime.worker_services(RabbitPublisher(broker, settings.publisher_timeout))
        register_payment_handler(broker, processor)
        await broker.connect()
        await declare_topology(broker)
        await broker.start()
        async with asyncio.TaskGroup() as tasks:
            dispatcher_task = tasks.create_task(
                dispatch_loop(broker, dispatcher, runtime.outbox_stats, stop, settings.outbox_poll_interval),
            )
            await stop.wait()
            dispatcher_task.cancel()


if __name__ == '__main__':
    configure_logging()
    asyncio.run(main())
