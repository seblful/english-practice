"""Tests for the bot's own settings."""

from pathlib import Path

import pytest
from practice_core.decisions import DecisionRoute
from practice_runtime.settings import LangSmithSettings, PathSettings
from pydantic import SecretStr

from practice_bot.settings import (
    BotSettings,
    DecisionSettings,
    Settings,
    TelegramSettings,
    get_settings,
)


def _runnable(tmp_path: Path) -> Settings:
    """Settings that pass every startup requirement."""
    database = tmp_path / "english_practice.db"
    database.touch()
    return Settings(
        telegram=TelegramSettings(bot_token=SecretStr("token"), admin_user_id=1),
        decision=DecisionSettings(google_api_key=SecretStr("key")),
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

    def test_reports_the_missing_key_of_the_chosen_route(self, tmp_path: Path) -> None:
        settings = _runnable(tmp_path)
        settings.decision.route = DecisionRoute.OPENROUTER

        assert any(
            "OPENROUTER_API_KEY is not set (DECISION_ROUTE=openrouter)" in p
            for p in settings.missing_required()
        )

    def test_needs_no_chat_model_key(self, tmp_path: Path) -> None:
        """Grading is the bot's only model call, and it is a decision."""
        assert "llm" not in Settings.model_fields
        assert _runnable(tmp_path).missing_required() == []

    def test_still_makes_the_shared_checks(self, tmp_path: Path) -> None:
        """The tracing key is the base class's job, and must not be lost."""
        settings = _runnable(tmp_path)
        settings.langsmith = LangSmithSettings(tracing=True, api_key=None)

        assert any("LANGSMITH_API_KEY" in p for p in settings.missing_required())

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


class TestDecisionSettings:
    def test_defaults_to_gemini_decision_through_google(self) -> None:
        """Google's free tier covers practice; OpenRouter has none."""
        settings = DecisionSettings()

        assert settings.route is DecisionRoute.GOOGLE
        assert settings.active_model == "gemini-decision-1"
        assert settings.key_variable == "GEMINI_API_KEY"

    def test_the_openrouter_route_names_its_own_model(self) -> None:
        settings = DecisionSettings(route=DecisionRoute.OPENROUTER)

        assert settings.active_model == "google/gemini-decision-1"
        assert settings.key_variable == "OPENROUTER_API_KEY"

    @pytest.mark.parametrize("model", [None, "", "  "])
    def test_a_blank_model_means_the_route_default(self, model: str | None) -> None:
        assert DecisionSettings(model=model).active_model == "gemini-decision-1"

    def test_the_key_follows_the_route(self) -> None:
        """An old .env holds both keys; the route decides which one is used."""
        settings = DecisionSettings(
            openrouter_api_key=SecretStr("or"), google_api_key=SecretStr("g")
        )

        assert settings.api_key == "g"
        settings.route = DecisionRoute.OPENROUTER
        assert settings.api_key == "or"

    def test_reads_the_providers_own_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "or")
        monkeypatch.setenv("GEMINI_API_KEY", "g")
        monkeypatch.setenv("GEMINI_PROXY", "http://proxy:8080")

        settings = DecisionSettings()

        assert settings.api_key == "g"
        assert settings.openrouter_api_key is not None
        assert settings.openrouter_api_key.get_secret_value() == "or"
        assert settings.proxy == "http://proxy:8080"

    def test_reads_its_prefixed_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DECISION_ROUTE", "google")
        monkeypatch.setenv("DECISION_GOOGLE_API_KEY", "dg")
        monkeypatch.setenv("DECISION_MODEL", "gemini-decision-2")
        monkeypatch.setenv("DECISION_PROXY", "socks5://localhost:9050")

        settings = DecisionSettings()

        assert settings.route is DecisionRoute.GOOGLE
        assert settings.api_key == "dg"
        assert settings.active_model == "gemini-decision-2"
        assert settings.proxy == "socks5://localhost:9050"

    def test_an_unknown_route_is_refused(self) -> None:
        with pytest.raises(ValueError, match="route"):
            DecisionSettings.model_validate({"route": "dashscope"})

    def test_a_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="request_timeout"):
            DecisionSettings(request_timeout=0)


class TestBotSettings:
    def test_a_session_cannot_expire_instantly(self) -> None:
        with pytest.raises(ValueError, match="session_idle_ttl_minutes"):
            BotSettings(session_idle_ttl_minutes=0)


def test_get_settings_is_cached() -> None:
    """The whole process shares one settings instance."""
    assert get_settings() is get_settings()
