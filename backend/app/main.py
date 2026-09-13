"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.constants import RATE_LIMIT_SWEEP_THRESHOLD_CLIENTS
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import TokenBucketLimiter
from app.error_handlers import register_error_handlers
from app.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.routes import (
    alerts,
    analysis,
    citizen,
    citizen_sensors,
    complaints,
    federation,
    guide,
    health,
    interop,
    official_aqi,
    operator,
    satellite,
)
from app.services.health_service import APP_VERSION

logger = get_logger(__name__)

#: Prefix for every versioned API route. The version is in the path rather than a
#: header so a partner city can pin a contract by URL alone.
API_PREFIX = "/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down hooks.

    ML artifacts are loaded here, once, rather than per request. Nothing is
    loaded yet at this stage of the build.
    """
    settings = get_settings()
    logger.info(
        "app.startup",
        environment=settings.environment,
        version=APP_VERSION,
    )
    yield
    logger.info("app.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Override settings, used by tests to avoid reading the real
            environment.

    Returns:
        A configured FastAPI application.
    """
    resolved = settings or get_settings()

    configure_logging(
        level=resolved.log_level,
        # Human-readable console output locally; one JSON object per line
        # everywhere a log aggregator will read it.
        json_output=resolved.environment != "development",
    )

    app = FastAPI(
        title="AirWatch",
        description=(
            "Federated hyperlocal air quality intelligence: hidden hotspot detection, "
            "wind back-trajectory source attribution, corridor forecasting, and "
            "cross-city model sharing without raw data exchange."
        ),
        version=APP_VERSION,
        lifespan=lifespan,
    )

    # Starlette runs the last middleware added first. Rate limiting is added
    # before the request context so a refused request still carries a request
    # ID and is logged, and CORS stays outermost so a browser can read the 429.
    # The limiter belongs to this app instance: state is per process, so each
    # worker enforces the limit on its own share of traffic.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=TokenBucketLimiter(
            resolved.rate_limit_per_minute,
            sweep_threshold=RATE_LIMIT_SWEEP_THRESHOLD_CLIENTS,
        ),
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(analysis.router, prefix=API_PREFIX)
    app.include_router(alerts.router, prefix=API_PREFIX)
    app.include_router(interop.router, prefix=API_PREFIX)
    app.include_router(citizen.router, prefix=API_PREFIX)
    app.include_router(citizen_sensors.router, prefix=API_PREFIX)
    app.include_router(complaints.router, prefix=API_PREFIX)
    app.include_router(federation.router, prefix=API_PREFIX)
    app.include_router(satellite.router, prefix=API_PREFIX)
    app.include_router(official_aqi.router, prefix=API_PREFIX)
    app.include_router(operator.router, prefix=API_PREFIX)
    app.include_router(guide.router, prefix=API_PREFIX)

    if settings is not None:
        # Routes resolve settings through Depends(get_settings), which returns the
        # process-wide cached singleton. When a caller supplies settings
        # explicitly — tests, or a federated node started with its own config —
        # that override has to reach the dependency too, or it would be silently
        # ignored and the app would run on the ambient environment instead.
        app.dependency_overrides[get_settings] = lambda: resolved

    return app


app = create_app()
