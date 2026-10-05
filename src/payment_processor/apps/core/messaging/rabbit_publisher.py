import asyncio

from aio_pika.exceptions import CONNECTION_EXCEPTIONS
from faststream.rabbit import RabbitBroker

from payment_processor.apps.core.errors import BrokerPublishError
from payment_processor.apps.outbox.dtos.outbox_message_dto import OutboxMessageDTO


class RabbitPublisher:
    def __init__(self, broker: RabbitBroker, timeout: float) -> None:
        self._broker = broker
        self._timeout = timeout

    async def publish(self, message: OutboxMessageDTO) -> None:
        try:
            async with asyncio.timeout(self._timeout):
                await self._broker.publish(
                    message.payload,
                    exchange=message.exchange,
                    routing_key=message.routing_key,
                    mandatory=True,
                    persist=True,
                    timeout=self._timeout,
                    message_id=str(message.id),
                    correlation_id=str(message.payment_id),
                    message_type=message.event_type,
                )
        except CONNECTION_EXCEPTIONS as exc:
            raise BrokerPublishError() from exc
