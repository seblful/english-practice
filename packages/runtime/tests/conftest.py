"""Shared fixtures for the runtime tests."""

import logging

import pytest
import structlog

from practice_runtime.settings import BaseAppSettings, project_root, settings_env_vars


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the developer's own environment from every test."""
    for name in settings_env_vars(BaseAppSettings):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _forget_project_root() -> None:
    """Keep a test that overrides the project root from leaking into the next."""
    project_root.cache_clear()


@pytest.fixture(autouse=True)
def _quiet_logging() -> None:
    """Drop application log records so test output stays readable."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.ReturnLoggerFactory(),
    )
