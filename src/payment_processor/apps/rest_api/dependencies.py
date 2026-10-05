from typing import Annotated, cast

from fastapi import Depends, Request

from payment_processor.apps.core.runtime import Runtime


async def get_runtime(request: Request) -> Runtime:
    return cast(Runtime, request.app.state.runtime)


RuntimeDependency = Annotated[Runtime, Depends(get_runtime)]
