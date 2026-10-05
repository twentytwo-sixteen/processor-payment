import ipaddress
from urllib.parse import urlsplit

from payment_processor.apps.payments.dtos.webhook_destination_policy_dto import WebhookDestinationPolicyDTO
from payment_processor.apps.payments.errors.base import WebhookDestinationError


class WebhookDestinationSpecification:
    class DestinationNotAllowedError(WebhookDestinationError):
        pass

    @classmethod
    def is_satisfied(cls, url: str, policy: WebhookDestinationPolicyDTO) -> bool:
        try:
            parts = urlsplit(url)
            host = (parts.hostname or '').lower()
            port = parts.port
        except ValueError:
            return False
        if port is not None and port < 1:
            return False
        if parts.username or parts.password or parts.fragment or host not in policy.allowed_hosts:
            return False
        if parts.scheme != 'https' and not (parts.scheme == 'http' and host in policy.private_hosts):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return address.is_global or host in policy.private_hosts

    @classmethod
    def affirm(cls, url: str, policy: WebhookDestinationPolicyDTO) -> None:
        if not cls.is_satisfied(url=url, policy=policy):
            raise cls.DestinationNotAllowedError()
