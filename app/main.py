from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import Settings
from app.services.database import GeoDatabase

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Show app INFO logs next to uvicorn's own output."""
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if not any(isinstance(handler, logging.StreamHandler) for handler in app_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        app_logger.addHandler(handler)
    app_logger.propagate = False


def create_app(
    settings: Settings | None = None,
    geo_db: GeoDatabase | None = None,
    *,
    start_database: bool = True,
) -> FastAPI:
    configure_logging()
    settings = settings or Settings()
    geo_db = geo_db or GeoDatabase(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        refresh_task: asyncio.Task[None] | None = None
        if start_database:
            try:
                await geo_db.start()
            except Exception:
                logger.exception("Failed to load geo database on start")
                raise SystemExit(1) from None
            refresh_task = asyncio.create_task(geo_db.refresh_loop())
        try:
            yield
        finally:
            if refresh_task is not None:
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
            await geo_db.close()

    app = FastAPI(title="IP to Location Service", lifespan=lifespan)
    app.state.settings = settings
    app.state.geo_db = geo_db
    app.include_router(router)
    return app


app = create_app()
