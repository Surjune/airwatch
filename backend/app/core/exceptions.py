"""Typed exception hierarchy.

Every failure path in AirWatch raises one of these. They carry a machine-readable
``code`` and a human-readable message, and the global handler maps them to a single
consistent JSON error envelope so no unhandled 500 ever reaches a client.

The rule that matters most: a missing credential or an unavailable upstream raises
an explicit error here. It never yields a fabricated or placeholder reading. In a
permit-and-enforcement context a wrong number is worse than an error.
"""

from __future__ import annotations

from typing import Any


class AirWatchError(Exception):
    """Base class for every error AirWatch raises deliberately.

    Attributes:
        code: Stable machine-readable identifier, safe to branch on in a client.
        message: Human-readable explanation, safe to show a user.
        status_code: HTTP status the global handler should return.
        details: Optional structured context, included in the error envelope.
    """

    code: str = "internal_error"
    status_code: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_envelope(self, request_id: str | None = None) -> dict[str, Any]:
        """Render the error as the JSON envelope returned to clients."""
        envelope: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            envelope["error"]["details"] = self.details
        if request_id is not None:
            envelope["error"]["request_id"] = request_id
        return envelope


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class ConfigurationError(AirWatchError):
    """The application is misconfigured and cannot serve the request."""

    code = "configuration_error"
    status_code = 500


class MissingCredentialError(ConfigurationError):
    """A required upstream credential is absent.

    Raised instead of degrading to synthetic data, which would silently turn an
    outage into a plausible-looking wrong answer.
    """

    code = "missing_credential"
    status_code = 503

    def __init__(self, provider: str, env_var: str) -> None:
        super().__init__(
            f"No credential configured for {provider}. Set {env_var} in the environment.",
            details={"provider": provider, "env_var": env_var},
        )


# ---------------------------------------------------------------------------
# Upstream data sources
# ---------------------------------------------------------------------------


class UpstreamError(AirWatchError):
    """Base class for failures talking to an external data provider."""

    code = "upstream_error"
    status_code = 502

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {"provider": provider}
        merged.update(details or {})
        super().__init__(message, details=merged)
        self.provider = provider


class UpstreamTimeoutError(UpstreamError):
    """An upstream did not respond within the configured timeout."""

    code = "upstream_timeout"
    status_code = 504


class UpstreamUnavailableError(UpstreamError):
    """An upstream returned a server error or could not be reached."""

    code = "upstream_unavailable"
    status_code = 503


class UpstreamResponseError(UpstreamError):
    """An upstream responded, but the payload was not in the expected shape.

    Treated as an error rather than being coerced, because a silently
    mis-parsed concentration is indistinguishable from a real reading.
    """

    code = "upstream_bad_response"
    status_code = 502


class UpstreamRateLimitedError(UpstreamError):
    """An upstream rejected the request for exceeding its quota."""

    code = "upstream_rate_limited"
    status_code = 429


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ValidationError(AirWatchError):
    """Input failed semantic validation beyond what the schema can express."""

    code = "validation_error"
    status_code = 422


class InvalidGeometryError(ValidationError):
    """A coordinate or geometry was structurally valid but semantically wrong."""

    code = "invalid_geometry"


class InvalidH3IndexError(ValidationError):
    """An H3 cell index was malformed or at an unsupported resolution."""

    code = "invalid_h3_index"


class UnsupportedPollutantError(ValidationError):
    """A pollutant outside the CPCB AQI set was requested."""

    code = "unsupported_pollutant"


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class NotFoundError(AirWatchError):
    """A requested resource does not exist."""

    code = "not_found"
    status_code = 404

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"No {resource} found with identifier {identifier!r}.",
            details={"resource": resource, "identifier": identifier},
        )


class InsufficientDataError(AirWatchError):
    """There is not enough data to produce a defensible answer.

    Distinct from NotFoundError: the resource exists, but answering would require
    extrapolating past what the observations support. Returning the shortfall is
    more useful than returning a confident-looking guess.
    """

    code = "insufficient_data"
    status_code = 422

    def __init__(self, message: str, *, required: int, available: int) -> None:
        super().__init__(message, details={"required": required, "available": available})


class ModelNotLoadedError(AirWatchError):
    """An inference was requested before its model artifact was loaded."""

    code = "model_not_loaded"
    status_code = 503

    def __init__(self, model_name: str) -> None:
        super().__init__(
            f"Model {model_name!r} is not loaded. Train it and restart the service.",
            details={"model": model_name},
        )


class AuthenticationRequiredError(AirWatchError):
    """An operator action was attempted without a valid operator key."""

    code = "authentication_required"
    status_code = 401

    def __init__(self) -> None:
        super().__init__("This action needs an operator key. Sign in as an operator to continue.")


class OperatorActionsDisabledError(AirWatchError):
    """No operator key is configured, so every operator action is refused."""

    code = "operator_actions_disabled"
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "Operator actions are disabled on this deployment: no OPERATOR_API_KEY is set."
        )


class RateLimitExceededError(AirWatchError):
    """The caller exceeded the per-IP or per-device rate limit."""

    code = "rate_limit_exceeded"
    status_code = 429
