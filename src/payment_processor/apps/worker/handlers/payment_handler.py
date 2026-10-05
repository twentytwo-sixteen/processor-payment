import asyncio
import logging

from faststream import AckPolicy
from faststream.rabbit import RabbitBroker
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.message import RabbitMessage as RawRabbitMessage
from pydantic import ValidationError

import payment_processor.constants.worker
from payment_processor.apps.core.messaging.topology import payment_exchange, payment_queue
from payment_processor.apps.core.observability import CONSUMER_MESSAGES, UNEXPECTED_ERRORS
from payment_processor.apps.core.services.errors import ServiceError, ServiceUnavailableError
from payment_processor.apps.payments.contracts.processing_event import PaymentProcessingRequested
from payment_processor.apps.payments.errors.base import LeaseBusyError, LeaseLostError
from payment_processor.apps.payments.services.process_payment_service import ProcessPaymentService

logger = logging.getLogger(__name__)


def raw_body(message: RawRabbitMessage) -> bytes:
    return bytes(message.body)


def register_payment_handler(broker: RabbitBroker, processor: ProcessPaymentService) -> None:
    @broker.subscriber(payment_queue, payment_exchange, ack_policy=AckPolicy.MANUAL, decoder=raw_body)
    async def handle_payment(body: bytes, msg: RabbitMessage) -> None:
        try:
            event = PaymentProcessingRequested.model_validate_json(body).to_dto()
        except ValidationError:
            CONSUMER_MESSAGES.labels(outcome='invalid').inc()
            await msg.reject(requeue=False)
            return
        delay = payment_processor.constants.worker.WORKER_CONSUMER_RECOVERY_DELAY_INITIAL_SECONDS
        while True:
            try:
                await processor.execute(event)
            except (ServiceUnavailableError, LeaseBusyError, LeaseLostError) as error:
                logger.warning(
                    'consumer_waiting',
                    extra={'error_code': error.code, 'event_id': str(event.event_id)},
                    exc_info=error,
                )
                await asyncio.sleep(delay)
                delay = min(
                    delay * payment_processor.constants.worker.WORKER_CONSUMER_RECOVERY_BACKOFF_MULTIPLIER,
                    payment_processor.constants.worker.WORKER_CONSUMER_RECOVERY_DELAY_MAX_SECONDS,
                )
                continue
            except ServiceError as error:
                logger.exception(
                    'consumer_service_error',
                    extra={'error_code': error.code, 'event_id': str(event.event_id)},
                )
            except Exception as error:
                UNEXPECTED_ERRORS.labels(boundary='consumer').inc()
                logger.exception(
                    'consumer_unexpected_error',
                    extra={'exception_type': type(error).__name__, 'event_id': str(event.event_id)},
                )
            else:
                await msg.ack()
                CONSUMER_MESSAGES.labels(outcome='handled').inc()
                return
            CONSUMER_MESSAGES.labels(outcome='dead_lettered').inc()
            await msg.reject(requeue=False)
            return
