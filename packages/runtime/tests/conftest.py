"""Shared fixtures for the runtime tests.

Nothing in this package reads the environment on its own — that is the property
these tests exist to protect — so the fixtures are about taking the developer's
own environment away and keeping deliberate log output out of pytest's report.
"""

import logging
from pathlib import Path

import pytest
import structlog

from practice_runtime.settings import BaseAppSettings, project_root, settings_env_vars


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the developer's own environment from every test.

    Each settings group is its own ``BaseSettings`` reading ``os.environ``
    through its prefix, so ``BaseAppSettings(_env_file=...)`` does not isolate
    them — an exported ``GEMINI_PROXY`` or ``PATHS_DATABASE_PATH`` would
    otherwise decide the outcome of a test that never mentions it.
    """
    for name in settings_env_vars(BaseAppSettings):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _forget_project_root() -> None:
    """Keep a test that overrides the project root from leaking into the next."""
    project_root.cache_clear()


@pytest.fixture(autouse=True)
def _quiet_logging() -> None:
    """Drop application log records so test output stays readable.

    This runs per test because the logging tests reconfigure structlog
    themselves.
    """
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.ReturnLoggerFactory(),
    )


@pytest.fixture
def tmp_env_file(tmp_path: Path) -> Path:
    """Create a temporary .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP__ENVIRONMENT=test\n", encoding="utf-8")
    return env_file
