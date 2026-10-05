from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas import Channel, QueueType

import payment_processor.constants.payments
import payment_processor.constants.worker

payment_exchange = RabbitExchange(payment_processor.constants.payments.PAYMENT_EXCHANGE, durable=True)
dead_exchange = RabbitExchange(payment_processor.constants.payments.PAYMENT_DEAD_EXCHANGE, durable=True)
payment_queue = RabbitQueue(
    payment_processor.constants.payments.PAYMENT_QUEUE,
    queue_type=QueueType.QUORUM,
    durable=True,
    routing_key=payment_processor.constants.payments.PAYMENT_QUEUE,
)
dead_queue = RabbitQueue(
    payment_processor.constants.payments.PAYMENT_DEAD_QUEUE,
    queue_type=QueueType.QUORUM,
    durable=True,
    routing_key=payment_processor.constants.payments.PAYMENT_DEAD_ROUTING_KEY,
)


def create_broker(url: str, concurrency: int) -> RabbitBroker:
    return RabbitBroker(
        url,
        default_channel=Channel(prefetch_count=concurrency, publisher_confirms=True, on_return_raises=True),
        graceful_timeout=payment_processor.constants.worker.WORKER_BROKER_SHUTDOWN_TIMEOUT_SECONDS,
        logger=None,
    )


async def declare_topology(broker: RabbitBroker) -> None:
    await broker.declare_exchange(payment_exchange)
    exchange = await broker.declare_exchange(dead_exchange)
    queue = await broker.declare_queue(dead_queue)
    await queue.bind(exchange, routing_key=payment_processor.constants.payments.PAYMENT_DEAD_ROUTING_KEY)
