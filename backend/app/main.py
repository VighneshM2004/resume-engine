"""FastAPI application factory.

`create_app` takes its settings and readiness checks as arguments so tests
can build an app with fakes and no network. Production uses the module-level
`app`, built from the environment.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import Settings, get_settings
from app.services.readiness import Check, default_checks, ensure_bucket, make_s3_client

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, checks: list[Check] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if checks is not None:
            app.state.readiness_checks = checks
        else:
            resolved = settings or get_settings()
            s3_client = make_s3_client(resolved)
            if resolved.s3_auto_create_bucket and resolved.app_env in ("dev", "test"):
                try:
                    ensure_bucket(resolved, s3_client)
                except Exception:
                    # Don't crash on startup: /ready will report storage as down.
                    logger.warning("could not ensure bucket at startup", exc_info=True)
            app.state.readiness_checks = default_checks(resolved, s3_client)
        yield

    app = FastAPI(
        title="resume-engine API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    return app


app = create_app()
