from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class PathSettings(BaseSettings):
    """File paths configuration."""

    data_dir: Path = BASE_DIR / "data"
    books_dir: Path = data_dir / "books"

    def create_directories(self) -> None:
        """Create all necessary directories."""
        for path in self.model_dump().values():
            path.mkdir(parents=True, exist_ok=True)


class BookSettings(BaseSettings):
    """Book settings."""

    original_file_name: str = "murphy.pdf"
    cut_file_name: str = "murphy_cut.pdf"
    start_page: int = 14
    end_page: int = 302


class ExerciseSettings(BaseSettings):
    """Exercise generation settings."""

    pass


class LLMSettings(BaseSettings):
    """LLM API settings."""

    pass


class TelegramSettings(BaseSettings):
    """Telegram bot configuration."""

    pass


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    # Application
    app_name: str = "English Practice"
    version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # Nested configs
    paths: PathSettings = Field(default_factory=PathSettings)
    book: BookSettings = Field(default_factory=BookSettings)
    exercises: ExerciseSettings = Field(default_factory=ExerciseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
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


settings = get_settings()
