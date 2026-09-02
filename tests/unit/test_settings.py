"""Unit tests for application settings."""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from english_practice.settings import (
    DashscopeSettings,
    GeminiSettings,
    LangSmithSettings,
    LLMSettings,
    PathSettings,
    Settings,
    TelegramSettings,
    get_settings,
    load_env,
    secret_value,
)


def _runnable_settings(tmp_path: Path) -> Settings:
    """Settings that pass every startup requirement."""
    database = tmp_path / "english_practice.db"
    database.touch()
    return Settings(
        telegram=TelegramSettings(bot_token=SecretStr("token"), admin_user_id=1),
        llm=LLMSettings(
            provider="dashscope",
            dashscope=DashscopeSettings(api_key=SecretStr("key")),
        ),
        paths=PathSettings(database_path=database),
    )


def test_settings_load_from_env_file(test_settings: Settings) -> None:
    """Nested settings are populated from the env file and defaults."""
    assert test_settings.app.environment == "test"
    assert test_settings.app.app_name == "english-practice"
    assert test_settings.app.secret_key is None
    assert test_settings.logging.console_level == "INFO"


class TestSecretValue:
    """Tests for unwrapping optional secrets."""

    def test_none_is_unset(self) -> None:
        assert secret_value(None) is None

    def test_blank_is_unset(self) -> None:
        assert secret_value(SecretStr("  ")) is None

    def test_returns_trimmed_text(self) -> None:
        assert secret_value(SecretStr(" token\n")) == "token"


class TestLoadEnv:
    """Tests for seeding os.environ from env files."""

    def test_environment_specific_file_wins_over_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("SHARED=base\nONLY_BASE=1\n", encoding="utf-8")
        (tmp_path / ".env.staging").write_text("SHARED=staging\n", encoding="utf-8")
        for name in ("SHARED", "ONLY_BASE"):
            monkeypatch.delenv(name, raising=False)

        applied = load_env(base_dir=tmp_path, environment="staging")

        assert applied["SHARED"] == "staging"
        assert applied["ONLY_BASE"] == "1"
        assert os.environ["SHARED"] == "staging"

    def test_real_environment_is_never_overwritten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A deployment's exported variable outranks a stale local file."""
        (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=stale\n", encoding="utf-8")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-deployment")

        applied = load_env(base_dir=tmp_path, environment="production")

        assert "TELEGRAM_BOT_TOKEN" not in applied
        assert os.environ["TELEGRAM_BOT_TOKEN"] == "from-deployment"

    def test_missing_files_are_ignored(self, tmp_path: Path) -> None:
        assert load_env(base_dir=tmp_path, environment="nope") == {}


class TestActiveApiKey:
    """Tests for resolving the selected provider's key."""

    def test_returns_selected_provider_key(self) -> None:
        config = LLMSettings(
            provider="dashscope",
            dashscope=DashscopeSettings(api_key=SecretStr("dash-key")),
        )
        assert config.active_api_key == "dash-key"

    def test_none_when_selected_provider_has_no_key(self) -> None:
        # Each group reads the process environment, so the unkeyed provider is
        # passed in explicitly rather than left to its default factory.
        config = LLMSettings(
            provider="gemini",
            gemini=GeminiSettings(api_key=None),
            dashscope=DashscopeSettings(api_key=SecretStr("dash-key")),
        )
        assert config.active_api_key is None


class TestMissingRequired:
    """Tests for the startup preflight check."""

    def test_runnable_configuration_has_no_problems(self, tmp_path: Path) -> None:
        assert _runnable_settings(tmp_path).missing_required() == []

    def test_reports_missing_bot_token(self, tmp_path: Path) -> None:
        settings = _runnable_settings(tmp_path)
        settings.telegram.bot_token = None

        assert any("TELEGRAM_BOT_TOKEN" in p for p in settings.missing_required())

    def test_reports_missing_admin_user_id(self, tmp_path: Path) -> None:
        settings = _runnable_settings(tmp_path)
        settings.telegram.admin_user_id = None

        assert any("TELEGRAM_ADMIN_USER_ID" in p for p in settings.missing_required())

    def test_reports_missing_provider_key(self, tmp_path: Path) -> None:
        settings = _runnable_settings(tmp_path)
        settings.llm.dashscope.api_key = None

        assert any("DASHSCOPE_API_KEY" in p for p in settings.missing_required())

    def test_reports_missing_langsmith_key_only_when_tracing(
        self, tmp_path: Path
    ) -> None:
        settings = _runnable_settings(tmp_path)
        settings.langsmith = LangSmithSettings(tracing=True, api_key=None)

        assert any("LANGSMITH_API_KEY" in p for p in settings.missing_required())

    def test_reports_missing_database(self, tmp_path: Path) -> None:
        settings = _runnable_settings(tmp_path)
        settings.paths.database_path = tmp_path / "absent.db"

        assert any("database not found" in p for p in settings.missing_required())


class TestPathSettings:
    """Tests for the filesystem layout."""

    def test_create_directories_skips_files(self, tmp_path: Path) -> None:
        paths = PathSettings(
            data_dir=tmp_path / "data",
            content_dir=tmp_path / "content",
            database_path=tmp_path / "content" / "app.db",
        )

        paths.create_directories()

        assert (tmp_path / "data").is_dir()
        assert not (tmp_path / "content" / "app.db").exists()

    def test_legacy_database_path_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The unprefixed DATABASE_PATH from older .env files still works."""
        monkeypatch.delenv("PATHS_DATABASE_PATH", raising=False)
        monkeypatch.setenv("DATABASE_PATH", "legacy/place.db")

        assert PathSettings().database_path == Path("legacy/place.db")


def test_get_settings_is_cached() -> None:
    """The whole process shares one settings instance."""
    assert get_settings() is get_settings()
