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
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    # A stdlib-backed factory is required, not merely preferred: the
    # add_logger_name processor reads `.name` off the underlying logger, and a
    # PrintLogger has no such attribute.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Rendering happens in a stdlib formatter rather than in the structlog chain
    # so that log lines from uvicorn, SQLAlchemy and httpx -- which know nothing
    # about structlog -- come out in the same shape as ours, and so a single
    # stream stays parseable end to end.
    #
    # format_exc_info belongs here and nowhere else. Placed in the structlog
    # chain it renders the traceback into the JSON, and then the stdlib formatter
    # prints the same traceback again as loose text, which breaks the guarantee
    # of one JSON object per line.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for a module.

    Args:
        name: Conventionally ``__name__`` of the calling module.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
