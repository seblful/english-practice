"""End-to-end tests for the CLI."""

from pathlib import Path

import pytest
from practice_runtime.errors import ConfigurationError
from typer.testing import CliRunner

from practice_bot.cli import app
from practice_bot.settings import Settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the generated logs/ directory out of the repository."""
    monkeypatch.chdir(tmp_path)


def test_info_command_succeeds() -> None:
    """`info` exits cleanly and describes the installation."""
    result = runner.invoke(app, ["info"])

    assert result.exit_code == 0
    assert "english-practice" in result.output
    assert "LLM provider:" in result.output


def test_check_command_reports_problems(monkeypatch: pytest.MonkeyPatch) -> None:
    """`check` fails with a list of what is missing."""
    monkeypatch.setattr(
        "practice_bot.cli.get_settings",
        lambda: _settings_with_problems(["TELEGRAM_BOT_TOKEN is not set"]),
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert "TELEGRAM_BOT_TOKEN is not set" in result.output


def test_check_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`check` succeeds when nothing is missing."""
    monkeypatch.setattr(
        "practice_bot.cli.get_settings", lambda: _settings_with_problems([])
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 0
    assert "looks good" in result.output


def test_bot_command_reports_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured bot exits with an explanation, not a traceback."""

    def explode(*_args: object, **_kwargs: object) -> None:
        raise ConfigurationError("cannot start the bot:\n  - nothing works")

    monkeypatch.setattr("practice_bot.app.run", explode)

    result = runner.invoke(app, ["bot"])

    assert result.exit_code == 1
    assert "nothing works" in result.output
    assert ".env.example" in result.output


def test_bot_command_runs_the_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """`bot` hands off to the application runner."""
    started = False

    def fake_run(*_args: object, **_kwargs: object) -> None:
        nonlocal started
        started = True

    monkeypatch.setattr("practice_bot.app.run", fake_run)

    result = runner.invoke(app, ["bot"])

    assert result.exit_code == 0
    assert started is True


def _settings_with_problems(problems: list[str]) -> Settings:
    """Return real settings that report the given problems."""

    class _Reporting(Settings):
        def missing_required(self) -> list[str]:
            return problems

    return _Reporting()
