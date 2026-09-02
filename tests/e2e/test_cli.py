"""End-to-end tests for the CLI."""

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from english_practice.cli import app
from english_practice.errors import ConfigurationError
from english_practice.packaging import BundleResult

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
        "english_practice.cli.get_settings",
        lambda: _settings_with_problems(["TELEGRAM_BOT_TOKEN is not set"]),
    )

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    assert "TELEGRAM_BOT_TOKEN is not set" in result.output


def test_check_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`check` succeeds when nothing is missing."""
    monkeypatch.setattr(
        "english_practice.cli.get_settings", lambda: _settings_with_problems([])
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

    monkeypatch.setattr("english_practice.bot.app.run", explode)

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

    monkeypatch.setattr("english_practice.bot.app.run", fake_run)

    result = runner.invoke(app, ["bot"])

    assert result.exit_code == 0
    assert started is True


def _settings_with_problems(problems: list[str]) -> object:
    """Return a stand-in settings object reporting the given problems."""

    class _Settings:
        def missing_required(self) -> list[str]:
            return problems

    return _Settings()


def test_mobile_content_command_builds_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mobile-content` reports the file it wrote and how much it saved."""
    built: dict[str, object] = {}

    def fake_build(
        source: Path,
        target: Path,
        schema: Path,
        *,
        progress: Callable[[str], None] | None = None,
    ) -> BundleResult:
        built.update(source=source, target=target, schema=schema)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"bundle")
        if progress is not None:
            progress("  units: 1 rows")
        return BundleResult(path=target, images=3, source_bytes=1000, bundled_bytes=100)

    monkeypatch.setattr("english_practice.packaging.build_mobile_content", fake_build)
    source = tmp_path / "source.db"
    source.write_bytes(b"")
    output = tmp_path / "content.db"

    result = runner.invoke(
        app,
        ["mobile-content", "--source", str(source), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert built["source"] == source
    assert built["target"] == output
    assert "units: 1 rows" in result.output
    assert "3 images" in result.output


def test_mobile_content_command_reports_a_missing_database(
    tmp_path: Path,
) -> None:
    """The message has to say which command builds the source database."""
    result = runner.invoke(
        app,
        [
            "mobile-content",
            "--source",
            str(tmp_path / "absent.db"),
            "--output",
            str(tmp_path / "out.db"),
        ],
    )

    assert result.exit_code == 1
    assert "populate.py" in result.output
