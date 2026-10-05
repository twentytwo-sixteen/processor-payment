import aiohttp
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from payment_processor.apps.core.database.health import DatabaseHealthDAO
from payment_processor.apps.core.database.ports import UnitOfWork
from payment_processor.apps.core.database.unit_of_work import SqlAlchemyUnitOfWork
from payment_processor.apps.core.services.health_check_service import HealthCheckService
from payment_processor.apps.outbox.ports import PublisherProtocol
from payment_processor.apps.outbox.services.get_outbox_stats_service import GetOutboxStatsService
from payment_processor.apps.outbox.services.publish_outbox_batch_service import PublishOutboxBatchService
from payment_processor.apps.payments.contracts.mappers import PaymentContractMapper
from payment_processor.apps.payments.dtos.webhook_destination_policy_dto import WebhookDestinationPolicyDTO
from payment_processor.apps.payments.infrastructure.clients.simulated_gateway import SimulatedGateway
from payment_processor.apps.payments.infrastructure.clients.webhook_client import ValidatedResolver, WebhookClient
from payment_processor.apps.payments.services.create_payment_service import CreatePaymentService
from payment_processor.apps.payments.services.get_payment_service import GetPaymentService
from payment_processor.apps.payments.services.process_payment_service import ProcessPaymentService
from payment_processor.apps.payments.services.schedule_payment_retry_service import SchedulePaymentRetryService
from payment_processor.apps.payments.services.send_payment_webhook_service import SendPaymentWebhookService
from payment_processor.settings.application import ApplicationSettings


class Runtime:
    def __init__(self, settings: ApplicationSettings) -> None:
        self.settings = settings
        self.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            pool_timeout=settings.database_pool_timeout_seconds,
            hide_parameters=True,
            connect_args={
                'server_settings': {
                    'statement_timeout': str(settings.database_statement_timeout_ms),
                    'lock_timeout': str(settings.database_lock_timeout_ms),
                    'application_name': 'payment-processor',
                },
            },
        )
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self._contracts = PaymentContractMapper()
        self._policy = WebhookDestinationPolicyDTO(
            allowed_hosts=frozenset(settings.webhook_allowed_hosts),
            private_hosts=frozenset(settings.webhook_private_hosts),
        )
        self._http: aiohttp.ClientSession | None = None
        self.create_payment = CreatePaymentService(
            _uow_factory=self.unit_of_work,
            _contracts=self._contracts,
            _webhook_policy=self._policy,
        )
        self.get_payment = GetPaymentService(_uow_factory=self.unit_of_work)
        self.health = HealthCheckService(_dao=DatabaseHealthDAO(self.engine))
        self.outbox_stats = GetOutboxStatsService(_uow_factory=self.unit_of_work)

    def unit_of_work(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self._sessions)

    async def worker_services(
        self,
        publisher: PublisherProtocol,
    ) -> tuple[ProcessPaymentService, PublishOutboxBatchService]:
        connector = aiohttp.TCPConnector(
            resolver=ValidatedResolver(self._policy),
            use_dns_cache=False,
            limit=self.settings.consumer_concurrency,
        )
        self._http = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(
                total=self.settings.webhook_timeout,
                connect=min(self.settings.webhook_connect_timeout_seconds, self.settings.webhook_timeout),
            ),
            trust_env=False,
        )
        webhook = SendPaymentWebhookService(
            _uow_factory=self.unit_of_work,
            _client=WebhookClient(session=self._http, policy=self._policy),
        )
        retry = SchedulePaymentRetryService(
            _uow_factory=self.unit_of_work,
            _contracts=self._contracts,
            _retry_base=self.settings.retry_base_seconds,
        )
        processor = ProcessPaymentService(
            _uow_factory=self.unit_of_work,
            _gateway=SimulatedGateway(
                delay_min=self.settings.gateway_delay_min,
                delay_max=self.settings.gateway_delay_max,
            ),
            _contracts=self._contracts,
            _webhook=webhook,
            _retry=retry,
            _lease_seconds=self.settings.processing_lease_seconds,
        )
        dispatcher = PublishOutboxBatchService(
            _uow_factory=self.unit_of_work,
            _publisher=publisher,
            _batch_size=self.settings.outbox_batch_size,
            _concurrency=self.settings.publisher_concurrency,
            _lease_seconds=self.settings.outbox_lease_seconds,
        )
        return processor, dispatcher

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()
        await self.engine.dispose()
