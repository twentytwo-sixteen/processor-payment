from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebhookDestinationPolicyDTO:
    allowed_hosts: frozenset[str]
    private_hosts: frozenset[str] = frozenset()
