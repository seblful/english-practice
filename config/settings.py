from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class PathSettings(BaseSettings):
    """File paths configuration."""

    data_dir: Path = BASE_DIR / "data"
    source_dir: Path = data_dir / "source"
    content_dir: Path = data_dir / "content"
    books_dir: Path = source_dir
    snippets_dir: Path = source_dir / "snippets"
    images_dir: Path = source_dir / "images"
    grammar_pages_dir: Path = images_dir / "grammar"
    exercises_pages_dir: Path = images_dir / "exercises"
    grammar_md_dir: Path = content_dir / "grammar"
    questions_dir: Path = content_dir / "questions"
    metadata_dir: Path = content_dir / "metadata"

    def create_directories(self) -> None:
        """Create all necessary directories."""
        for path in self.model_dump().values():
            path.mkdir(parents=True, exist_ok=True)


class BookSettings(BaseSettings):
    """Book settings."""

    filename: str = "murphy.pdf"


class ImageSettings(BaseSettings):
    """Images settings."""

    pages_dpi: int = 300


class ExerciseSettings(BaseSettings):
    """Exercise generation settings."""

    pass


class OcrSettings(BaseSettings):
    """OCR settings (Mistral API for image text extraction)."""

    api_key: str | None = None
    model: str = "mistral-ocr-latest"


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
    images: ImageSettings = Field(default_factory=ImageSettings)
    exercises: ExerciseSettings = Field(default_factory=ExerciseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
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


settings = get_settings()
