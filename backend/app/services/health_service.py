"""Health and configuration reporting.

Thin by design, but it lives in the service layer rather than the route so the
route keeps its single responsibility: parse, call one service, return.
"""

from __future__ import annotations

from app.core.config import CREDENTIAL_SOURCES, Settings
from app.core.constants import H3_RESOLUTION
from app.schemas.health import HealthResponse, UpstreamStatus

#: Application version, surfaced so a node can tell which build a peer is running
#: before exchanging model weights with it.
APP_VERSION = "0.1.0"


def build_health_report(settings: Settings) -> HealthResponse:
    """Summarise liveness and which upstreams are configured.

    Args:
        settings: The process settings singleton.

    Returns:
        A health report naming any upstream whose credential is absent, so a
        misconfiguration is visible immediately rather than at the first
        ingestion run.
    """
    upstreams = [
        UpstreamStatus(
            provider=provider,
            configured=settings.has(attribute),
            required_env_var=env_var,
        )
        for attribute, (provider, env_var) in CREDENTIAL_SOURCES.items()
    ]

    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=APP_VERSION,
        h3_resolution=H3_RESOLUTION,
        upstreams=upstreams,
    )
