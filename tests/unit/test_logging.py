"""Unit tests for logging setup."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from english_practice.logging import setup_logging


def _clear_root() -> None:
    """Drop root handlers so setup_logging runs past its idempotency guard.

    pytest installs its own capture handler around each test, which would
    otherwise make setup_logging return early.
    """
    for handler in list(logging.root.handlers):
        logging.root.removeHandler(handler)
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    """Restore a clean logging state after each test."""
    yield
    _clear_root()


def test_setup_logging_attaches_handlers(tmp_path: Path) -> None:
    """File and console handlers are attached and the log file dir is created."""
    _clear_root()
    log_file = tmp_path / "app.log"
    setup_logging(log_file=log_file)

    assert any(isinstance(h, logging.FileHandler) for h in logging.root.handlers)
    assert log_file.parent.exists()


def test_setup_logging_is_idempotent(tmp_path: Path) -> None:
    """A second call is a no-op while handlers are already configured."""
    _clear_root()
    setup_logging(log_file=tmp_path / "app.log")
    count = len(logging.root.handlers)

    setup_logging(log_file=tmp_path / "app.log")
    assert len(logging.root.handlers) == count
