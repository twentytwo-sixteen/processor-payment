import asyncio
import hashlib
import random
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import payment_processor.constants.payments
from payment_processor.apps.payments.dtos.payment_dto import GatewayResultDTO


@dataclass(slots=True)
class SimulatedGateway:
    delay_min: float = payment_processor.constants.payments.PAYMENT_GATEWAY_DELAY_MIN_SECONDS
    delay_max: float = payment_processor.constants.payments.PAYMENT_GATEWAY_DELAY_MAX_SECONDS

    async def process(self, payment_id: UUID, amount: Decimal, currency: str) -> GatewayResultDTO:
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))
        digest = hashlib.sha256(payment_id.bytes).digest()
        bucket = int.from_bytes(digest[: payment_processor.constants.payments.PAYMENT_GATEWAY_HASH_PREFIX_BYTES])
        declined = bucket % payment_processor.constants.payments.PAYMENT_GATEWAY_DECLINE_BUCKETS == 0
        return GatewayResultDTO(
            status=payment_processor.constants.payments.PaymentStatus.FAILED
            if declined
            else payment_processor.constants.payments.PaymentStatus.SUCCEEDED,
            reference=f'sim-{payment_id}',
            failure_code=payment_processor.constants.payments.PAYMENT_GATEWAY_FAILURE_DECLINED if declined else None,
        )
