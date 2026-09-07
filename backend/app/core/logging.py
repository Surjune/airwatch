"""Structured JSON logging with per-request correlation.

Never use ``print``. Every log line carries the request's correlation ID, bound to
a context variable so it propagates automatically into services, repositories and
external clients without being threaded through every function signature.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

#: Correlation ID for the request currently being handled. Set by the middleware
#: at the edge and read by the structlog processor on every line emitted.
_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Generate a correlation ID for a request that arrived without one."""
    return uuid.uuid4().hex


def bind_request_id(request_id: str) -> None:
    """Bind a correlation ID to the current context."""
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Return the correlation ID bound to the current context, if any."""
    return _request_id_var.get()


def _add_request_id(
    _logger: object,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor injecting the bound correlation ID into every line."""
    request_id = _request_id_var.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    """Configure structlog and the stdlib root logger.

    Args:
        level: Minimum level to emit.
        json_output: Emit one JSON object per line. Disabled in local development
            where a human-readable console renderer is easier to scan.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_request_id,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib loggers (uvicorn, sqlalchemy, httpx) through the same handler
    # so a single log stream stays parseable.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for a module.

    Args:
        name: Conventionally ``__name__`` of the calling module.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
