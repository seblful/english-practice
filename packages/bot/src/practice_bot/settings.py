"""The bot's settings: the shared groups, plus Telegram."""

from functools import lru_cache

from practice_core.providers import DEFAULT_PROVIDER, Provider
from practice_runtime.settings import (
    BaseAppSettings,
    env_var,
    group_config,
    load_settings,
    secret_value,
)
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings
from telegram import Update

__all__ = [
    "BotSettings",
    "GraderSettings",
    "Settings",
    "TelegramSettings",
    "get_settings",
]


class TelegramSettings(BaseSettings):
    """Telegram transport configuration."""

    model_config = group_config("telegram")

    bot_token: SecretStr | None = None
    admin_user_id: int | None = None
    connect_timeout: int = 30
    read_timeout: int = 60
    write_timeout: int = 60
    pool_timeout: int = 60
    concurrent_updates: bool = True
    close_loop: bool = False
    allowed_updates: list[str] = Field(default_factory=lambda: list(Update.ALL_TYPES))


class GraderSettings(BaseSettings):
    """The decision model that grades answers, and the provider that runs it.

    The provider's key and proxy are its own group's: GEMINI_* or OPENROUTER_*.
    """

    model_config = group_config("grader")

    provider: Provider = Field(
        default=DEFAULT_PROVIDER, description="gemini (default) or openrouter"
    )
    model: str | None = Field(
        default=None,
        description="Any decision model that accepts images; the provider's "
        "Gemini Decision 1 when unset",
    )
    request_timeout: float = Field(
        default=30.0, gt=0, description="Per-request timeout in seconds"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Retries for transient provider failures"
    )

    @property
    def active_model(self) -> str:
        """Return the model to grade with: the one set, or Gemini Decision 1."""
        return (self.model or "").strip() or self.provider.decision_model


class BotSettings(BaseSettings):
    """Behaviour of the practice bot itself."""

    model_config = group_config("bot")

    session_idle_ttl_minutes: int = Field(
        default=720,
        ge=1,
        description="Idle time after which an in-memory user session is evicted",
    )


class Settings(BaseAppSettings):
    """Everything the bot needs to run."""

    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    grader: GraderSettings = Field(default_factory=GraderSettings)
    bot: BotSettings = Field(default_factory=BotSettings)

    def missing_required(self) -> list[str]:
        """Return human-readable reasons the bot cannot start."""
        problems = super().missing_required()

        missing = self.missing_key(
            self.grader.provider, env_var(self.grader, "provider")
        )
        if missing is not None:
            problems.append(missing)

        if secret_value(self.telegram.bot_token) is None:
            problems.append(f"{env_var(self.telegram, 'bot_token')} is not set")

        if self.telegram.admin_user_id is None:
            # Without an admin the bot would start and refuse every user.
            problems.append(f"{env_var(self.telegram, 'admin_user_id')} is not set")

        if not self.paths.database_path.exists():
            problems.append(
                f"database not found at {self.paths.database_path} "
                "(run: uv run practice-content populate)"
            )

        return problems


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading env files on first use."""
    return load_settings(Settings)
