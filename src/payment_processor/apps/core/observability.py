import json
import logging
from traceback import extract_tb

from prometheus_client import Counter, Gauge

CONSUMER_MESSAGES = Counter('payment_consumer_messages_total', 'Consumer outcomes', ['outcome'])
OUTBOX_PENDING = Gauge('payment_outbox_pending', 'Unpublished durable events')
OUTBOX_AGE = Gauge('payment_outbox_oldest_age_seconds', 'Age of oldest unpublished event')
UNEXPECTED_ERRORS = Counter('payment_unexpected_errors_total', 'Unexpected boundary failures', ['boundary'])


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {'level': record.levelname, 'message': record.getMessage(), 'logger': record.name}
        for name in (
            'payment_id',
            'event_id',
            'attempt',
            'status',
            'error_code',
            'request_id',
            'exception_type',
            'http_status',
        ):
            if hasattr(record, name):
                data[name] = getattr(record, name)
        if record.exc_info is not None and record.exc_info[1] is not None:
            data['exception_chain'] = self._exception_chain(record.exc_info[1])
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _exception_chain(error: BaseException) -> list[dict[str, object]]:

        chain: list[dict[str, object]] = []
        seen: set[int] = set()
        current: BaseException | None = error
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            chain.append(
                {
                    'type': type(current).__name__,
                    'frames': [
                        {'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
                        for frame in extract_tb(current.__traceback__)
                    ],
                },
            )
            if current.__cause__ is not None:
                current = current.__cause__
            elif not current.__suppress_context__:
                current = current.__context__
            else:
                current = None
        return chain


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
