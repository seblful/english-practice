"""Tests for the bot's own settings.

The shared groups are `practice-runtime`'s and are tested there. What is
checked here is what only the bot has: Telegram, and the preflight that decides
whether it may start at all.
"""

from pathlib import Path

import pytest
from practice_runtime.settings import DashscopeSettings, LLMSettings, PathSettings
from pydantic import SecretStr

from practice_bot.settings import BotSettings, Settings, TelegramSettings, get_settings


def _runnable(tmp_path: Path) -> Settings:
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


class TestMissingRequired:
    def test_a_runnable_configuration_has_no_problems(self, tmp_path: Path) -> None:
        assert _runnable(tmp_path).missing_required() == []

    def test_reports_missing_bot_token(self, tmp_path: Path) -> None:
        settings = _runnable(tmp_path)
        settings.telegram.bot_token = None

        assert any("TELEGRAM_BOT_TOKEN" in p for p in settings.missing_required())

    def test_reports_missing_admin_user_id(self, tmp_path: Path) -> None:
        """Without an admin nobody could ever be approved."""
        settings = _runnable(tmp_path)
        settings.telegram.admin_user_id = None

        assert any("TELEGRAM_ADMIN_USER_ID" in p for p in settings.missing_required())

    def test_reports_a_missing_database(self, tmp_path: Path) -> None:
        settings = _runnable(tmp_path)
        settings.paths.database_path = tmp_path / "absent.db"

        problems = settings.missing_required()

        assert any("database not found" in p for p in problems)
        assert any("practice-content populate" in p for p in problems)

    def test_still_makes_the_shared_checks(self, tmp_path: Path) -> None:
        """The provider key is the base class's job, and must not be lost."""
        settings = _runnable(tmp_path)
        settings.llm.dashscope.api_key = None

        assert any("DASHSCOPE_API_KEY" in p for p in settings.missing_required())

    def test_reports_everything_at_once(self, tmp_path: Path) -> None:
        """One round trip: the bot should not be fixed one variable at a time."""
        settings = _runnable(tmp_path)
        settings.telegram.bot_token = None
        settings.telegram.admin_user_id = None
        settings.paths.database_path = tmp_path / "absent.db"

        assert len(settings.missing_required()) == 3


class TestTelegramSettings:
    def test_asks_for_every_update_type_by_default(self) -> None:
        assert "message" in TelegramSettings().allowed_updates

    def test_reads_its_prefixed_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TELEGRAM_ADMIN_USER_ID", "42")

        assert TelegramSettings().admin_user_id == 42


class TestBotSettings:
    def test_a_transcript_needs_room_for_a_turn(self) -> None:
        with pytest.raises(ValueError, match="max_history_messages"):
            BotSettings(max_history_messages=1)

    def test_a_session_cannot_expire_instantly(self) -> None:
        with pytest.raises(ValueError, match="session_idle_ttl_minutes"):
            BotSettings(session_idle_ttl_minutes=0)


def test_get_settings_is_cached() -> None:
    """The whole process shares one settings instance."""
    assert get_settings() is get_settings()
