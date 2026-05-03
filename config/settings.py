import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from telegram import Update

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    """Load environment variables from .env and .env.{environment}."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)

    environment = os.environ.get("ENVIRONMENT", "development")
    env_specific = BASE_DIR / f".env.{environment}"
    if env_specific.exists():
        load_dotenv(env_specific, override=True)


class PathSettings(BaseSettings):
    """File paths configuration."""

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
    database_path: Path | None = None

    def create_directories(self) -> None:
        """Create all necessary directories."""
        for name, path in self.model_dump().items():
            if (
                path is not None
                and isinstance(path, Path)
                and not path.suffix  # Skip files (paths with extensions)
            ):
                path.mkdir(parents=True, exist_ok=True)


class BookSettings(BaseSettings):
    """Book settings."""

    filename: str = "murphy.pdf"


class ImageSettings(BaseSettings):
    """Images settings."""

    pages_dpi: int = 300


class OcrSettings(BaseSettings):
    """OCR settings (Mistral API for image text extraction)."""

    api_key: str | None = None
    model: str = "mistral-ocr-latest"


class DashscopeSettings(BaseSettings):
    """DashScope API settings."""

    model_config = SettingsConfigDict(
        env_prefix="DASHSCOPE_",
        case_sensitive=False,
    )

    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    api_key: str | None = None
    model: str = "qwen3-vl-flash-2026-01-22"
    temperature: float = 0.7
    max_tokens: int = 2048


class GeminiSettings(BaseSettings):
    """Gemini API settings."""

    model_config = SettingsConfigDict(
        env_prefix="GEMINI_",
        case_sensitive=False,
    )

    api_key: str | None = None
    model: str = "gemini-2.5-flash-lite"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    proxy: str | None = None


class OpenRouterSettings(BaseSettings):
    """OpenRouter API settings."""

    model_config = SettingsConfigDict(
        env_prefix="OPENROUTER_",
        case_sensitive=False,
    )

    api_key: str | None = None
    model: str = "openai/gpt-4o-mini"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMSettings(BaseSettings):
    """LLM provider settings."""

    provider: Literal["dashscope", "gemini", "openrouter"] = "dashscope"
    dashscope: DashscopeSettings = Field(default_factory=DashscopeSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)


class LangSmithSettings(BaseSettings):
    """LangSmith settings for tracing."""

    model_config = SettingsConfigDict(
        env_prefix="LANGSMITH_",
        case_sensitive=False,
    )

    api_key: str | None = None
    project: str = "english-practice"
    tracing: bool = True


class TelegramSettings(BaseSettings):
    """Telegram bot configuration."""

    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        case_sensitive=False,
    )

    bot_token: str | None = None
    admin_user_id: int | None = None
    connect_timeout: int = 30
    read_timeout: int = 60
    write_timeout: int = 60
    pool_timeout: int = 60
    concurrent_updates: bool = True
    close_loop: bool = False
    allowed_updates: list[str] = Update.ALL_TYPES


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "English Practice"
    version: str = "0.1.0"
    debug: bool = False

    # Nested configs
    paths: PathSettings = Field(default_factory=PathSettings)
    book: BookSettings = Field(default_factory=BookSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    ocr: OcrSettings = Field(default_factory=OcrSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: str | None = "logs/app.log"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        return v.upper()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings."""
    settings = Settings()
    settings.paths.create_directories()
    return settings


# Load env and create settings
_load_env()
settings = get_settings()
