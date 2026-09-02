"""Application settings.

Every setting is resolved from the environment through pydantic-settings, so the
process environment is the single source of truth. Files only seed it: values
already exported by the shell, Docker, or CI always win over a checked-out
``.env`` (see :func:`load_env`).

Settings are read through :func:`get_settings`, which caches one instance for
the process. Importing this module has no side effects — nothing is read and no
directory is created until that function is called.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Update

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMProvider = Literal["dashscope", "gemini", "openrouter"]

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Environment is chosen by an OS variable (set in the shell, Dockerfile, or CI).
# Missing env files are silently ignored, so .env.<environment> is optional.
_ENVIRONMENT_VAR = "APP__ENVIRONMENT"
_DEFAULT_ENVIRONMENT = "development"


def secret_value(secret: SecretStr | None) -> str | None:
    """Return the plain text behind an optional secret.

    Args:
        secret: The secret to unwrap, if one is configured.

    Returns:
        The secret's text, or ``None`` when it is unset or blank. Blank counts
        as unset so that ``KEY=`` in an env file does not read as configured.
    """
    if secret is None:
        return None
    return secret.get_secret_value().strip() or None


def load_env(
    base_dir: Path | None = None,
    environment: str | None = None,
) -> dict[str, str]:
    """Seed ``os.environ`` from ``.env`` and ``.env.{environment}``.

    The nested settings groups below are each ``BaseSettings`` in their own
    right and resolve flat variables such as ``TELEGRAM_BOT_TOKEN`` from the
    process environment, so env files have to be materialised there before any
    group is constructed.

    Precedence, highest first: the real process environment, then
    ``.env.{environment}``, then ``.env``. Variables that are already exported
    are never overwritten — a deployment that passes ``TELEGRAM_BOT_TOKEN`` in
    the environment must not be silently downgraded to a stale local file.

    Args:
        base_dir: Directory holding the env files. Defaults to the repo root.
        environment: Environment name selecting ``.env.{environment}``.
            Defaults to ``$APP__ENVIRONMENT``, or ``development``.

    Returns:
        The variables this call actually set, for logging and tests.
    """
    root = base_dir or BASE_DIR
    env_name = environment or os.getenv(_ENVIRONMENT_VAR, _DEFAULT_ENVIRONMENT)

    # Later files win over earlier ones, so the environment-specific file
    # overrides the shared base file.
    from_files: dict[str, str] = {}
    for env_file in (root / ".env", root / f".env.{env_name}"):
        if not env_file.exists():
            continue
        from_files.update(
            {
                key: value
                for key, value in dotenv_values(env_file, encoding="utf-8").items()
                if value is not None
            }
        )

    applied = {k: v for k, v in from_files.items() if k not in os.environ}
    os.environ.update(applied)
    return applied


class AppSettings(BaseModel):
    """Application identity and environment."""

    app_name: str = Field(default="english-practice", description="Application name")
    environment: str = Field(
        default=_DEFAULT_ENVIRONMENT, description="Environment name"
    )
    secret_key: SecretStr | None = Field(
        default=None, description="Application secret (set via APP__SECRET_KEY)"
    )


class LoggingSettings(BaseModel):
    """Logging destinations and verbosity."""

    file_level: LogLevel = Field(default="INFO", description="File log level")
    console_level: LogLevel = Field(default="INFO", description="Console log level")
    log_file: Path = Field(default=Path("logs/app.log"), description="Log file path")


class PathSettings(BaseSettings):
    """Filesystem layout for source material, generated content, and the database."""

    # populate_by_name lets tests and callers pass `database_path=...` directly,
    # which an explicit validation_alias would otherwise shadow.
    model_config = SettingsConfigDict(
        env_prefix="PATHS_", case_sensitive=False, populate_by_name=True
    )

    app_dir: Path = BASE_DIR / "src" / "english_practice"
    prompts_dir: Path = app_dir / "agents" / "prompts"

    data_dir: Path = BASE_DIR / "data"
    source_dir: Path = data_dir / "source"
    content_dir: Path = data_dir / "content"
    snippets_dir: Path = source_dir / "snippets"
    images_dir: Path = source_dir / "images"
    grammar_pages_dir: Path = images_dir / "grammar"
    exercises_pages_dir: Path = images_dir / "exercises"
    grammar_md_dir: Path = content_dir / "grammar"
    exercises_dir: Path = content_dir / "exercises"
    metadata_dir: Path = content_dir / "metadata"

    # DATABASE_PATH is accepted as a legacy alias: this group was unprefixed
    # before, and existing .env files set the bare name.
    database_path: Path = Field(
        default=content_dir / "english_practice.db",
        validation_alias=AliasChoices("PATHS_DATABASE_PATH", "DATABASE_PATH"),
        description="SQLite database file",
    )

    def create_directories(self) -> None:
        """Create every configured directory.

        Only the extraction pipeline needs the source and content tree to
        exist, so this is called explicitly by that entry point rather than on
        import.
        """
        for path in self.model_dump().values():
            if (
                isinstance(path, Path)
                and not path.suffix  # Skip files (paths with extensions)
            ):
                path.mkdir(parents=True, exist_ok=True)


class BookSettings(BaseSettings):
    """Source book location."""

    model_config = SettingsConfigDict(env_prefix="BOOK_", case_sensitive=False)

    filename: str = "murphy.pdf"


class ImageSettings(BaseSettings):
    """Page rendering options for the extraction pipeline."""

    model_config = SettingsConfigDict(env_prefix="IMAGES_", case_sensitive=False)

    pages_dpi: int = 300


class OcrSettings(BaseSettings):
    """Mistral OCR settings for the extraction pipeline."""

    # API_KEY is accepted as a legacy alias: this group was unprefixed before.
    model_config = SettingsConfigDict(
        env_prefix="OCR_", case_sensitive=False, populate_by_name=True
    )

    api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OCR_API_KEY", "MISTRAL_API_KEY", "API_KEY"),
    )
    model: str = "mistral-ocr-latest"


class DashscopeSettings(BaseSettings):
    """DashScope (Alibaba) OpenAI-compatible endpoint."""

    model_config = SettingsConfigDict(env_prefix="DASHSCOPE_", case_sensitive=False)

    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    api_key: SecretStr | None = None
    model: str = "qwen3-vl-flash-2026-01-22"
    temperature: float = 0.7
    max_tokens: int = 2048


class GeminiSettings(BaseSettings):
    """Google Gemini API settings."""

    model_config = SettingsConfigDict(env_prefix="GEMINI_", case_sensitive=False)

    api_key: SecretStr | None = None
    model: str = "gemini-2.5-flash-lite"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    proxy: str | None = None


class OpenRouterSettings(BaseSettings):
    """OpenRouter API settings."""

    model_config = SettingsConfigDict(env_prefix="OPENROUTER_", case_sensitive=False)

    api_key: SecretStr | None = None
    model: str = "google/gemma-4-26b-a4b-it"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMSettings(BaseSettings):
    """Which LLM provider to use, and each provider's configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_", case_sensitive=False)

    provider: LLMProvider = "dashscope"
    request_timeout: float = Field(
        default=60.0, gt=0, description="Per-request timeout in seconds"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Retries for transient provider failures"
    )
    dashscope: DashscopeSettings = Field(default_factory=DashscopeSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)

    @property
    def active_api_key(self) -> str | None:
        """Return the API key of the selected provider, if configured."""
        provider_settings: DashscopeSettings | GeminiSettings | OpenRouterSettings = {
            "dashscope": self.dashscope,
            "gemini": self.gemini,
            "openrouter": self.openrouter,
        }[self.provider]
        return secret_value(provider_settings.api_key)


class LangSmithSettings(BaseSettings):
    """LangSmith tracing settings."""

    model_config = SettingsConfigDict(env_prefix="LANGSMITH_", case_sensitive=False)

    api_key: SecretStr | None = None
    project: str = "english-practice"
    tracing: bool = False


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
    max_exercise_attempts: int = Field(
        default=5,
        ge=1,
        description="Draws attempted before giving up on finding a usable exercise",
    )


class Settings(BaseSettings):
    """Application settings with ``__``-delimited nested groups."""

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # Project-specific groups.
    paths: PathSettings = Field(default_factory=PathSettings)
    book: BookSettings = Field(default_factory=BookSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    ocr: OcrSettings = Field(default_factory=OcrSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    bot: BotSettings = Field(default_factory=BotSettings)

    # `extra="ignore"` rather than the template's "forbid": the env files also
    # carry the flat, prefixed variables consumed by the groups above, which are
    # not fields of this model.
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    def missing_required(self) -> list[str]:
        """Return human-readable reasons the app cannot start.

        Returns:
            One message per misconfiguration; empty when the app can run.
        """
        problems: list[str] = []

        if secret_value(self.telegram.bot_token) is None:
            problems.append("TELEGRAM_BOT_TOKEN is not set")

        if self.llm.active_api_key is None:
            problems.append(
                f"{self.llm.provider.upper()}_API_KEY is not set "
                f"(LLM__PROVIDER={self.llm.provider})"
            )

        if self.langsmith.tracing and secret_value(self.langsmith.api_key) is None:
            problems.append("LANGSMITH_API_KEY is required when tracing is enabled")

        if not self.paths.database_path.exists():
            problems.append(
                f"database not found at {self.paths.database_path} "
                "(run: uv run scripts/database/populate.py)"
            )

        return problems


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading env files on first use.

    Returns:
        The cached settings instance.
    """
    load_env()
    return Settings()
