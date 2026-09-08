"""Tests for settings loading and credential resolution.

The behaviour under test is the project's central safety rule: a missing
credential raises, and never falls back to something that looks like data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import CREDENTIAL_SOURCES, Settings
from app.core.exceptions import MissingCredentialError


class TestCredentialResolution:
    def test_require_returns_a_configured_credential(self, configured_settings: Settings) -> None:
        assert configured_settings.require("firms_map_key") == "test-firms-key"

    def test_require_raises_a_typed_error_when_absent(self, settings: Settings) -> None:
        with pytest.raises(MissingCredentialError) as excinfo:
            settings.require("firms_map_key")

        error = excinfo.value
        assert error.code == "missing_credential"
        # The error must name the variable to set, or the operator has to go
        # reading source to fix a deployment.
        assert error.details["env_var"] == "FIRMS_MAP_KEY"
        assert error.details["provider"] == "NASA FIRMS"

    def test_whitespace_only_credential_counts_as_absent(self, settings: Settings) -> None:
        blank = settings.model_copy(update={"firms_map_key": "   "})
        with pytest.raises(MissingCredentialError):
            blank.require("firms_map_key")

    def test_unknown_credential_is_a_programming_error(self, settings: Settings) -> None:
        with pytest.raises(KeyError):
            settings.require("not_a_real_credential")

    @pytest.mark.parametrize("credential", sorted(CREDENTIAL_SOURCES))
    def test_every_registered_credential_resolves_or_raises(
        self, settings: Settings, credential: str
    ) -> None:
        # No registered credential may quietly return a default value.
        with pytest.raises(MissingCredentialError):
            settings.require(credential)

    def test_has_reports_presence_without_raising(
        self, settings: Settings, configured_settings: Settings
    ) -> None:
        assert settings.has("openaq_api_key") is False
        assert configured_settings.has("openaq_api_key") is True


class TestOriginParsing:
    """A mode="before" validator accepts the comma-separated string that an
    environment variable actually delivers, as well as the declared list[str].
    """

    def test_splits_a_comma_separated_string(self) -> None:
        parsed = Settings(cors_allowed_origins="http://a.test, http://b.test")
        assert parsed.cors_allowed_origins == ["http://a.test", "http://b.test"]

    def test_accepts_a_list_unchanged(self) -> None:
        parsed = Settings(cors_allowed_origins=["http://a.test"])
        assert parsed.cors_allowed_origins == ["http://a.test"]

    def test_ignores_empty_entries(self) -> None:
        parsed = Settings(cors_allowed_origins="http://a.test,,  ,")
        assert parsed.cors_allowed_origins == ["http://a.test"]


class TestDotEnvParsing:
    """Regression cover for values arriving from a real .env file.

    Constructing Settings(...) in Python bypasses the dotenv source entirely, so
    the original tests passed while a real .env file crashed the application at
    startup. These load through the file, which is the path that actually runs.
    """

    def test_reads_a_single_origin_from_a_dotenv_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("CORS_ALLOWED_ORIGINS=http://localhost:5173", encoding="utf-8")

        parsed = Settings(_env_file=env_file)

        assert parsed.cors_allowed_origins == ["http://localhost:5173"]

    def test_reads_several_comma_separated_origins(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173",
            encoding="utf-8",
        )

        parsed = Settings(_env_file=env_file)

        assert parsed.cors_allowed_origins == [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

    def test_reads_credentials_from_a_dotenv_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("FIRMS_MAP_KEY=abc123", encoding="utf-8")

        parsed = Settings(_env_file=env_file)

        assert parsed.require("firms_map_key") == "abc123"
