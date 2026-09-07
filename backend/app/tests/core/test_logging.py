"""Tests for the logging configuration.

These exist because a misconfigured processor chain does not fail at import; it
fails on the first line actually emitted. An earlier version paired a stdlib
processor with a non-stdlib logger factory and only crashed at application
startup, because the test suite ran at WARNING and never emitted an info line.
Every test here therefore emits at the level it is checking.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest

from app.core.logging import (
    bind_request_id,
    configure_logging,
    get_logger,
    get_request_id,
    new_request_id,
)


def _raise_upstream_failure() -> None:
    """Raise from a helper so the test body keeps a single responsibility."""
    raise RuntimeError("upstream exploded")


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Leave logging configured at WARNING so other tests stay quiet."""
    yield
    configure_logging(level="WARNING", json_output=True)
    logging.getLogger().handlers.clear()


class TestConfigureLogging:
    def test_emits_at_info_without_raising(self, capsys: pytest.CaptureFixture[str]) -> None:
        # The regression case: this call is what crashed application startup.
        configure_logging(level="INFO", json_output=True)
        get_logger(__name__).info("app.startup", environment="test")

        captured = capsys.readouterr().out
        assert "app.startup" in captured

    def test_json_output_is_one_parseable_object_per_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(level="INFO", json_output=True)
        get_logger(__name__).info("ingestion.completed", rows=42)

        line = capsys.readouterr().out.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["event"] == "ingestion.completed"
        assert payload["rows"] == 42
        assert payload["level"] == "info"
        # The logger name is what makes a line traceable to a module.
        assert payload["logger"] == __name__
        assert "timestamp" in payload

    def test_console_renderer_does_not_raise(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="INFO", json_output=False)
        get_logger(__name__).info("app.startup")
        assert "app.startup" in capsys.readouterr().out

    def test_level_filtering_suppresses_lower_levels(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(level="ERROR", json_output=True)
        logger = get_logger(__name__)
        logger.info("should.not.appear")
        logger.error("should.appear")

        captured = capsys.readouterr().out
        assert "should.not.appear" not in captured
        assert "should.appear" in captured

    def test_exception_logging_includes_the_traceback(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(level="INFO", json_output=True)
        try:
            _raise_upstream_failure()
        except RuntimeError:
            get_logger(__name__).exception("request.unhandled_error")

        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert "RuntimeError: upstream exploded" in payload["exception"]


class TestRequestCorrelation:
    def test_new_ids_are_unique(self) -> None:
        assert new_request_id() != new_request_id()

    def test_bound_id_appears_on_every_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="INFO", json_output=True)
        bind_request_id("correlation-under-test")
        get_logger(__name__).info("service.called")

        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        # This is what lets a single request be traced across the service,
        # repository and external-client boundaries.
        assert payload["request_id"] == "correlation-under-test"

    def test_bound_id_is_readable(self) -> None:
        bind_request_id("readable-id")
        assert get_request_id() == "readable-id"
