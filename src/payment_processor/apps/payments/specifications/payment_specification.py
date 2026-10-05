import json
from decimal import Decimal, InvalidOperation

import payment_processor.constants.payments
from payment_processor.apps.payments.dtos.payment_dto import CreatePaymentDTO
from payment_processor.apps.payments.errors.base import PaymentRuleViolationError


class PaymentSpecification:
    class InvalidPaymentError(PaymentRuleViolationError):
        pass

    @classmethod
    def is_satisfied(cls, command: CreatePaymentDTO) -> bool:
        return (
            cls._amount_is_valid(command.amount) and cls._fields_are_valid(command) and cls._metadata_is_valid(command)
        )

    @classmethod
    def affirm(cls, command: CreatePaymentDTO) -> None:
        if not cls.is_satisfied(command=command):
            raise cls.InvalidPaymentError()

    @staticmethod
    def _amount_is_valid(amount: Decimal) -> bool:
        if not amount.is_finite() or not 0 < amount <= payment_processor.constants.payments.PAYMENT_AMOUNT_MAX:
            return False
        try:
            quantized = amount.quantize(payment_processor.constants.payments.PAYMENT_AMOUNT_QUANTUM)
        except InvalidOperation:
            return False
        return amount == quantized

    @staticmethod
    def _fields_are_valid(command: CreatePaymentDTO) -> bool:
        return (
            payment_processor.constants.payments.PAYMENT_IDEMPOTENCY_KEY_MIN_LENGTH
            <= len(command.idempotency_key)
            <= payment_processor.constants.payments.PAYMENT_IDEMPOTENCY_KEY_MAX_LENGTH
            and bool(command.idempotency_key.strip())
            and len(command.description) <= payment_processor.constants.payments.PAYMENT_DESCRIPTION_MAX_LENGTH
        )

    @staticmethod
    def _metadata_is_valid(command: CreatePaymentDTO) -> bool:
        try:
            encoded = json.dumps(command.metadata, allow_nan=False, ensure_ascii=False).encode()
        except (ValueError, TypeError):
            return False
        return len(encoded) <= payment_processor.constants.payments.PAYMENT_METADATA_MAX_BYTES
