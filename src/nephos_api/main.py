from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from nephos_api import __version__
from nephos_api.config import Settings, get_settings
from nephos_api.errors import NephosError, nephos_error_handler
from nephos_api.reconciler import BackgroundReconciler
from nephos_api.routers.apps import router as apps_router
from nephos_api.routers.bindings import router as bindings_router
from nephos_api.routers.catalog import router as catalog_router
from nephos_api.routers.platform_domains import router as platform_domains_router
from nephos_api.routers.services import router as services_router


def create_app(settings: Settings | None = None, *, start_reconciler: bool = False) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker: BackgroundReconciler | None = None
        if start_reconciler:
            worker = BackgroundReconciler(resolved_settings)
            await worker.start()
            app.state.reconciler = worker
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()

    app = FastAPI(title="Nephos API", version=__version__, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.add_exception_handler(NephosError, nephos_error_handler)
    app.include_router(apps_router)
    app.include_router(bindings_router)
    app.include_router(catalog_router)
    app.include_router(services_router)
    app.include_router(platform_domains_router)

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"version": __version__}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app(start_reconciler=True)

