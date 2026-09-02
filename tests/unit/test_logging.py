"""Unit tests for logging setup."""

import io
import logging
import sys
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


def test_setup_logging_rewraps_a_non_utf8_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a cp1252 console, emoji in log records would otherwise raise."""
    _clear_root()
    original = sys.stderr
    monkeypatch.setattr(
        sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    )

    setup_logging(log_file=tmp_path / "app.log")

    assert sys.stderr.encoding == "utf-8"
    monkeypatch.setattr(sys, "stderr", original)


def test_setup_logging_honours_explicit_levels(tmp_path: Path) -> None:
    """Levels passed in win over the configured ones."""
    _clear_root()

    setup_logging(
        file_level="ERROR", console_level="DEBUG", log_file=tmp_path / "app.log"
    )

    levels = {handler.level for handler in logging.root.handlers}
    assert levels == {logging.ERROR, logging.DEBUG}


def test_setup_logging_is_idempotent(tmp_path: Path) -> None:
    """A second call is a no-op while handlers are already configured."""
    _clear_root()
    setup_logging(log_file=tmp_path / "app.log")
    count = len(logging.root.handlers)

    setup_logging(log_file=tmp_path / "app.log")
    assert len(logging.root.handlers) == count
