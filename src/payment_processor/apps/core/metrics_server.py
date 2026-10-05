import hmac
import json
from collections.abc import Iterable
from http import HTTPStatus
from socketserver import ThreadingMixIn
from threading import Thread
from typing import cast
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server
from wsgiref.types import StartResponse, WSGIEnvironment

from prometheus_client import make_wsgi_app

import payment_processor.constants.http
import payment_processor.constants.worker


class MetricsServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def start_authenticated_metrics(api_key: str) -> WSGIServer:
    original = make_wsgi_app()
    expected_key = api_key.encode()
    authentication_error = json.dumps(
        {
            'error': {
                'code': payment_processor.constants.http.HTTP_ERROR_AUTHENTICATION_CODE,
                'message': payment_processor.constants.http.HTTP_ERROR_AUTHENTICATION_MESSAGE,
            },
        },
        separators=(',', ':'),
    ).encode()

    def authenticate(environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
        supplied_key = str(environ.get(payment_processor.constants.http.HTTP_WSGI_API_KEY_ENVIRON_NAME, '')).encode()
        if not hmac.compare_digest(supplied_key, expected_key):
            error_status = HTTPStatus.UNAUTHORIZED
            start_response(
                f'{error_status.value} {error_status.phrase}',
                [
                    (
                        payment_processor.constants.http.HTTP_HEADER_CONTENT_TYPE,
                        payment_processor.constants.http.HTTP_MEDIA_TYPE_JSON,
                    )
                ],
            )
            return [authentication_error]
        return cast(Iterable[bytes], original(environ, start_response))

    server = make_server(
        payment_processor.constants.http.HTTP_SERVER_BIND_HOST,
        payment_processor.constants.worker.WORKER_METRICS_PORT,
        authenticate,
        server_class=MetricsServer,
        handler_class=QuietHandler,
    )
    Thread(target=server.serve_forever, daemon=True).start()
    return server
