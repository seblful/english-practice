"""End-to-end tests for the CLI."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from english_practice.cli import app

runner = CliRunner()


def test_info_command_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`info` exits cleanly and prints the application name."""
    monkeypatch.chdir(tmp_path)  # keep the generated logs/ out of the repo
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "english-practice" in result.output
