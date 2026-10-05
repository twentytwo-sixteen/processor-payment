import ipaddress
import socket
from http import HTTPStatus
from uuid import UUID

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import ThreadedResolver

import payment_processor.constants.webhooks
from payment_processor.apps.core.types import JsonObject
from payment_processor.apps.payments.dtos.webhook_destination_policy_dto import WebhookDestinationPolicyDTO
from payment_processor.apps.payments.errors.base import (
    WebhookDestinationError,
    WebhookPermanentError,
    WebhookRetryableError,
)
from payment_processor.apps.payments.specifications.webhook_destination_specification import (
    WebhookDestinationSpecification,
)


class ValidatedResolver(AbstractResolver):
    def __init__(self, policy: WebhookDestinationPolicyDTO) -> None:
        self._resolver = ThreadedResolver()
        self._policy = policy

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET) -> list[ResolveResult]:
        normalized_host = host.lower()
        if normalized_host not in self._policy.allowed_hosts:
            raise WebhookPermanentError()
        addresses = await self._resolver.resolve(host, port, socket.AddressFamily(family))
        if normalized_host not in self._policy.private_hosts and any(
            not ipaddress.ip_address(item['host']).is_global for item in addresses
        ):
            raise WebhookPermanentError()
        return addresses

    async def close(self) -> None:
        await self._resolver.close()


class WebhookClient:
    def __init__(self, session: aiohttp.ClientSession, policy: WebhookDestinationPolicyDTO) -> None:
        self._session = session
        self._policy = policy

    async def send(self, url: str, event_id: UUID, payload: JsonObject) -> None:
        try:
            WebhookDestinationSpecification.affirm(url=url, policy=self._policy)
        except WebhookDestinationError as exc:
            raise WebhookPermanentError() from exc
        try:
            response_status = await self._post(url, event_id, payload)
        except aiohttp.ClientSSLError as exc:
            raise WebhookPermanentError() from exc
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise WebhookRetryableError() from exc
        self._check_response(response_status)

    async def _post(self, url: str, event_id: UUID, payload: JsonObject) -> int:
        async with self._session.post(
            url,
            json=payload,
            headers={payment_processor.constants.webhooks.WEBHOOK_EVENT_ID_HEADER: str(event_id)},
            allow_redirects=False,
        ) as response:
            if HTTPStatus.OK <= response.status < HTTPStatus.MULTIPLE_CHOICES:
                await response.content.read(payment_processor.constants.webhooks.WEBHOOK_RESPONSE_READ_MAX_BYTES)
            return response.status

    @staticmethod
    def _check_response(response_status: int) -> None:
        if HTTPStatus.OK <= response_status < HTTPStatus.MULTIPLE_CHOICES:
            return
        if response_status in (HTTPStatus.REQUEST_TIMEOUT, HTTPStatus.TOO_MANY_REQUESTS) or (
            response_status >= HTTPStatus.INTERNAL_SERVER_ERROR
        ):
            raise WebhookRetryableError(http_status=response_status)
        raise WebhookPermanentError(http_status=response_status)
