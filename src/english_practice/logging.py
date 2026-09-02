"""Logging configuration using structlog."""

import io
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

from english_practice.settings import get_settings

# Third-party loggers that are chatty at INFO and below.
_NOISY_LOGGERS = ("google_genai", "httpx", "httpcore")


def setup_logging(
    file_level: str | None = None,
    console_level: str | None = None,
    log_file: Path | None = None,
) -> None:
    """Configure structlog for the application."""
    if logging.root.handlers:
        return

    settings = get_settings()
    # Level names are constrained by the LogLevel Literal, so each maps to a logging
    # constant. getattr is unambiguous and works on every supported Python version.
    f_level: int = getattr(logging, (file_level or settings.logging.file_level).upper())
    c_level: int = getattr(
        logging, (console_level or settings.logging.console_level).upper()
    )

    file_path = (log_file or settings.logging.log_file).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        file_path, maxBytes=10_485_760, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(f_level)

    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(c_level)

    logging.basicConfig(
        format="%(message)s",
        level=min(f_level, c_level),
        handlers=[file_handler, console_handler],
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.app.environment == "production"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            # Keeps the timestamp the standard-library formatter used to add.
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(min(f_level, c_level)),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Suppress noisy third-party loggers.
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        A structlog logger bound to ``name``.
    """
    return structlog.get_logger(name)
