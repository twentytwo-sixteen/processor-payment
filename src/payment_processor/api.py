from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

import payment_processor.constants.http
from payment_processor.apps.core.observability import configure_logging
from payment_processor.apps.core.runtime import Runtime
from payment_processor.apps.rest_api.exception_handlers import register_exception_handlers
from payment_processor.apps.rest_api.security.middleware import APIBoundaryMiddleware
from payment_processor.apps.rest_api.v1.payments.payment_routes import router
from payment_processor.settings.application import ApplicationSettings


def create_app(settings: ApplicationSettings | None = None) -> FastAPI:
    config = settings or ApplicationSettings()
    runtime = Runtime(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(title='Payment Processor', version='0.1.0', lifespan=lifespan)
    app.state.runtime = runtime
    app.add_middleware(
        APIBoundaryMiddleware,
        api_key=config.api_key.get_secret_value(),
        max_body=config.max_request_bytes,
    )
    register_exception_handlers(app)
    app.include_router(router)

    @app.get('/health/ready', include_in_schema=False)
    async def readiness() -> dict[str, str]:
        await runtime.health.execute()
        return {'status': 'ready'}

    @app.get('/metrics', include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


if __name__ == '__main__':
    configure_logging()
    uvicorn.run(
        create_app(),
        host=payment_processor.constants.http.HTTP_SERVER_BIND_HOST,
        port=payment_processor.constants.http.HTTP_API_SERVER_PORT,
        log_config=None,
        access_log=False,
    )
