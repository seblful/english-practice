"""The bot's settings: the shared groups, plus Telegram."""

from functools import lru_cache

from practice_runtime.settings import BaseAppSettings, load_settings, secret_value
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Update

__all__ = ["BotSettings", "Settings", "TelegramSettings", "get_settings"]


class TelegramSettings(BaseSettings):
    """Telegram transport configuration."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", case_sensitive=False)

    bot_token: SecretStr | None = None
    admin_user_id: int | None = None
    connect_timeout: int = 30
    read_timeout: int = 60
    write_timeout: int = 60
    pool_timeout: int = 60
    concurrent_updates: bool = True
    close_loop: bool = False
    allowed_updates: list[str] = Field(default_factory=lambda: list(Update.ALL_TYPES))


class BotSettings(BaseSettings):
    """Behaviour of the practice bot itself."""

    model_config = SettingsConfigDict(env_prefix="BOT_", case_sensitive=False)

    max_history_messages: int = Field(
        default=20,
        ge=2,
        description="Assistant turns kept per exercise before the oldest are dropped",
    )
    session_idle_ttl_minutes: int = Field(
        default=720,
        ge=1,
        description="Idle time after which an in-memory user session is evicted",
    )


class Settings(BaseAppSettings):
    """Everything the bot needs to run."""

    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    bot: BotSettings = Field(default_factory=BotSettings)

    def missing_required(self) -> list[str]:
        """Return human-readable reasons the bot cannot start."""
        problems = super().missing_required()

        if secret_value(self.telegram.bot_token) is None:
            problems.append("TELEGRAM_BOT_TOKEN is not set")

        if self.telegram.admin_user_id is None:
            # Without an admin the bot would start and refuse every user.
            problems.append("TELEGRAM_ADMIN_USER_ID is not set")

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
