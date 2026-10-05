import hmac
from uuid import UUID, uuid4

from starlette import status
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import ClientDisconnect, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import payment_processor.constants.http
from payment_processor.apps.core.errors import RequestBodyTooLargeError
from payment_processor.apps.rest_api.exception_handlers import error_response


class APIBoundaryMiddleware:
    def __init__(self, app: ASGIApp, api_key: str, max_body: int) -> None:
        self._app = app
        self._api_key = api_key.encode()
        self._max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = self._request_id(headers)
        scope.setdefault('state', {})['request_id'] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message['type'] == 'http.response.start':
                MutableHeaders(scope=message)[payment_processor.constants.http.HTTP_HEADER_REQUEST_ID] = request_id
            await send(message)

        supplied_key = headers.get(payment_processor.constants.http.HTTP_HEADER_API_KEY, '').encode(
            payment_processor.constants.http.HTTP_HEADER_ENCODING,
        )
        if not hmac.compare_digest(supplied_key, self._api_key):
            await error_response(
                status.HTTP_401_UNAUTHORIZED,
                payment_processor.constants.http.HTTP_ERROR_AUTHENTICATION_CODE,
                payment_processor.constants.http.HTTP_ERROR_AUTHENTICATION_MESSAGE,
                request_id,
            )(scope, receive, send_with_request_id)
            return
        try:
            body = await self._read_body(Request(scope, receive))
        except ClientDisconnect:
            return
        except RequestBodyTooLargeError:
            await error_response(
                status.HTTP_413_CONTENT_TOO_LARGE,
                payment_processor.constants.http.HTTP_ERROR_BODY_TOO_LARGE_CODE,
                payment_processor.constants.http.HTTP_ERROR_BODY_TOO_LARGE_MESSAGE,
                request_id,
            )(scope, receive, send_with_request_id)
            return
        await self._app(scope, self._replay_body(body, receive), send_with_request_id)

    async def _read_body(self, request: Request) -> bytes:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > self._max_body:
                raise RequestBodyTooLargeError()
            body.extend(chunk)
        return bytes(body)

    @staticmethod
    def _request_id(headers: Headers) -> str:
        try:
            return str(UUID(headers.get(payment_processor.constants.http.HTTP_HEADER_REQUEST_ID, '')))
        except ValueError:
            return str(uuid4())

    @staticmethod
    def _replay_body(body: bytes, receive: Receive) -> Receive:
        consumed = False

        async def replay_receive() -> Message:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()

        return replay_receive
