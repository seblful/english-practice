"""The bot's settings: the shared groups, plus Telegram."""

from functools import lru_cache

from practice_core.decisions import DEFAULT_ROUTE, DecisionRoute
from practice_runtime.settings import BaseAppSettings, load_settings, secret_value
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Update

__all__ = [
    "BotSettings",
    "DecisionSettings",
    "Settings",
    "TelegramSettings",
    "get_settings",
]


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


class DecisionSettings(BaseSettings):
    """The decision model that grades answers, and the route it is reached by."""

    model_config = SettingsConfigDict(
        env_prefix="DECISION_", case_sensitive=False, populate_by_name=True
    )

    route: DecisionRoute = Field(
        default=DEFAULT_ROUTE, description="google (default) or openrouter"
    )
    # The providers' own variable names work too, so an existing .env carries over.
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DECISION_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"
        ),
    )
    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DECISION_GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )
    model: str | None = Field(
        default=None,
        description="Any decision model that accepts images; the route's Gemini "
        "Decision 1 when unset",
    )
    proxy: str | None = Field(
        default=None, validation_alias=AliasChoices("DECISION_PROXY", "GEMINI_PROXY")
    )
    request_timeout: float = Field(
        default=30.0, gt=0, description="Per-request timeout in seconds"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Retries for transient provider failures"
    )

    @property
    def api_key(self) -> str | None:
        """Return the key the selected route needs, if configured."""
        if self.route is DecisionRoute.OPENROUTER:
            return secret_value(self.openrouter_api_key)
        return secret_value(self.google_api_key)

    @property
    def key_variable(self) -> str:
        """Return the variable that holds the selected route's key."""
        return _KEY_VARIABLES[self.route]

    @property
    def active_model(self) -> str:
        """Return the model to grade with on the selected route."""
        return (self.model or "").strip() or self.route.default_model


_KEY_VARIABLES = {
    DecisionRoute.OPENROUTER: "OPENROUTER_API_KEY",
    DecisionRoute.GOOGLE: "GEMINI_API_KEY",
}


class BotSettings(BaseSettings):
    """Behaviour of the practice bot itself."""

    model_config = SettingsConfigDict(env_prefix="BOT_", case_sensitive=False)

    session_idle_ttl_minutes: int = Field(
        default=720,
        ge=1,
        description="Idle time after which an in-memory user session is evicted",
    )


class Settings(BaseAppSettings):
    """Everything the bot needs to run."""

    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    decision: DecisionSettings = Field(default_factory=DecisionSettings)
    bot: BotSettings = Field(default_factory=BotSettings)

    def missing_required(self) -> list[str]:
        """Return human-readable reasons the bot cannot start."""
        problems = super().missing_required()

        if self.decision.api_key is None:
            problems.append(
                f"{self.decision.key_variable} is not set "
                f"(DECISION_ROUTE={self.decision.route})"
            )

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
