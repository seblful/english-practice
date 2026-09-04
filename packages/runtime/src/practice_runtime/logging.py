"""One structlog configuration, for whichever program is running."""

import io
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

from practice_runtime.settings import LoggingSettings

__all__ = ["get_logger", "setup_logging"]

# Third-party loggers that are chatty at INFO and below.
_NOISY_LOGGERS = ("google_genai", "httpx", "httpcore")

_MAX_LOG_BYTES = 10_485_760
_LOG_BACKUPS = 3


def setup_logging(
    config: LoggingSettings | None = None,
    *,
    json_logs: bool = False,
) -> None:
    """Configure structlog for the process."""
    if logging.root.handlers:
        return

    config = config or LoggingSettings()
    # The LogLevel Literal constrains the names, so getattr is unambiguous.
    file_level: int = getattr(logging, config.file_level.upper())
    console_level: int = getattr(logging, config.console_level.upper())

    file_path = Path(config.log_file).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_LOG_BACKUPS,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)

    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)

    logging.basicConfig(
        format="%(message)s",
        level=min(file_level, console_level),
        handlers=[file_handler, console_handler],
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
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
        wrapper_class=structlog.make_filtering_bound_logger(
            min(file_level, console_level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance."""
    return structlog.get_logger(name)
