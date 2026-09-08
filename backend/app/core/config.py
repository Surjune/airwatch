"""Application configuration, loaded once from the environment.

Credentials are deliberately optional at load time and validated at point of use
via :meth:`Settings.require`. A missing key must fail the one call that needs it
with a typed error, not prevent the whole service from starting -- ingestion of
FIRMS fire data should not be blocked because an OpenAQ key is absent.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.exceptions import MissingCredentialError

#: Repository root, resolved from this file: core -> app -> backend -> repo root.
REPO_ROOT: Path = Path(__file__).resolve().parents[3]

#: Maps a settings attribute to the provider name and environment variable
#: reported when it is missing.
CREDENTIAL_SOURCES: dict[str, tuple[str, str]] = {
    "openaq_api_key": ("OpenAQ", "OPENAQ_API_KEY"),
    "cpcb_api_key": ("CPCB (data.gov.in)", "CPCB_API_KEY"),
    "firms_map_key": ("NASA FIRMS", "FIRMS_MAP_KEY"),
    "gee_service_account_email": ("Google Earth Engine", "GEE_SERVICE_ACCOUNT_EMAIL"),
}


class Settings(BaseSettings):
    """Environment-driven settings for the API and the ingestion workers."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Application ---------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_port: Annotated[int, Field(ge=1, le=65535)] = 8000

    #: Comma-separated in the environment, split into a list by the validator.
    #: NoDecode is required, not decorative: without it pydantic-settings tries to
    #: JSON-decode any complex-typed value coming from a dotenv file and raises
    #: before the validator below ever runs, so a perfectly ordinary
    #: `CORS_ALLOWED_ORIGINS=http://localhost:5173` would stop the app booting.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # -- Infrastructure ------------------------------------------------------
    database_url: str = "postgresql+psycopg://airwatch:airwatch@localhost:5433/airwatch"
    redis_url: str = "redis://localhost:6380/0"

    # -- Upstream credentials ------------------------------------------------
    # Empty means absent. Never substitute a default: a placeholder key would
    # surface as a confusing upstream 401 rather than a clear configuration error.
    openaq_api_key: str = ""
    cpcb_api_key: str = ""
    firms_map_key: str = ""

    # -- Optional, Phase 5 ---------------------------------------------------
    gee_service_account_email: str = ""
    gee_private_key_path: str = ""

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string from the environment."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def require(self, credential: str) -> str:
        """Return a credential, raising a typed error when it is absent.

        Args:
            credential: Attribute name on this settings object, for example
                ``"firms_map_key"``.

        Raises:
            MissingCredentialError: The credential is empty. The caller must
                propagate this rather than falling back to synthetic data.
        """
        if credential not in CREDENTIAL_SOURCES:
            raise KeyError(f"{credential!r} is not a registered credential")

        value = str(getattr(self, credential, "")).strip()
        if not value:
            provider, env_var = CREDENTIAL_SOURCES[credential]
            raise MissingCredentialError(provider, env_var)
        return value

    def has(self, credential: str) -> bool:
        """Whether a credential is configured, without raising.

        Used by the health endpoint to report which upstreams are reachable.
        """
        return bool(str(getattr(self, credential, "")).strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
