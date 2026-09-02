"""Tests for logging setup."""

import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from practice_runtime.logging import get_logger, setup_logging
from practice_runtime.settings import LoggingSettings


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


def _config(tmp_path: Path, **overrides: object) -> LoggingSettings:
    """Logging settings writing into a scratch directory."""
    fields: dict[str, object] = {"log_file": tmp_path / "logs" / "app.log"}
    fields.update(overrides)
    return LoggingSettings.model_validate(fields)


def test_attaches_handlers_and_creates_the_log_directory(tmp_path: Path) -> None:
    _clear_root()

    setup_logging(_config(tmp_path))

    assert any(isinstance(h, logging.FileHandler) for h in logging.root.handlers)
    assert (tmp_path / "logs").is_dir()


def test_rewraps_a_non_utf8_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a cp1252 console, emoji in log records would otherwise raise."""
    _clear_root()
    original = sys.stderr
    monkeypatch.setattr(
        sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    )

    setup_logging(_config(tmp_path))

    assert sys.stderr.encoding == "utf-8"
    monkeypatch.setattr(sys, "stderr", original)


def test_honours_the_configured_levels(tmp_path: Path) -> None:
    _clear_root()

    setup_logging(_config(tmp_path, file_level="ERROR", console_level="DEBUG"))

    levels = {handler.level for handler in logging.root.handlers}
    assert levels == {logging.ERROR, logging.DEBUG}


def test_defaults_are_usable_without_settings(tmp_path: Path) -> None:
    """A one-off script should not have to build a settings model first."""
    _clear_root()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    try:
        setup_logging()
    finally:
        monkeypatch.undo()

    assert logging.root.handlers


def test_is_idempotent(tmp_path: Path) -> None:
    """A second call is a no-op while handlers are already configured."""
    _clear_root()
    setup_logging(_config(tmp_path))
    count = len(logging.root.handlers)

    setup_logging(_config(tmp_path))

    assert len(logging.root.handlers) == count


def test_json_logs_are_opt_in(tmp_path: Path) -> None:
    """A deployment has something reading its log; a laptop has a human."""
    _clear_root()

    setup_logging(_config(tmp_path), json_logs=True)
    get_logger("test").info("hello", key="value")

    written = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert '"key": "value"' in written


def test_console_logs_are_the_default(tmp_path: Path) -> None:
    _clear_root()

    setup_logging(_config(tmp_path))
    get_logger("test").info("hello", key="value")

    written = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "key" in written
    assert '"key": "value"' not in written
