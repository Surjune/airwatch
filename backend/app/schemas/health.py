"""Response models for the health endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UpstreamStatus(BaseModel):
    """Whether one upstream data source is usable.

    ``configured`` reports only that a credential is present. It deliberately
    does not call the upstream: a health check that fans out to four third-party
    APIs fails whenever any of them is slow, which makes it useless as a liveness
    probe.
    """

    provider: str = Field(description="Human-readable provider name.")
    configured: bool = Field(description="Whether a credential is present for this provider.")
    required_env_var: str = Field(description="Environment variable that supplies the credential.")


class HealthResponse(BaseModel):
    """Service liveness and configuration summary."""

    status: Literal["ok"] = Field(description="Liveness indicator.")
    environment: str = Field(description="Deployment environment name.")
    version: str = Field(description="Application version.")
    h3_resolution: int = Field(
        description="Canonical H3 analysis resolution. Nodes must agree on this to exchange models."
    )
    upstreams: list[UpstreamStatus] = Field(
        description="Configuration state of each upstream data source."
    )
