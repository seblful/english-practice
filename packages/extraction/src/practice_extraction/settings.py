"""The pipeline's settings: the shared groups, plus the book and the OCR."""

from functools import lru_cache

from practice_runtime.settings import (
    LLMAppSettings,
    env_var,
    group_config,
    load_settings,
    secret_value,
)
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

__all__ = [
    "DEFAULT_OCR_MODEL",
    "BookSettings",
    "ImageSettings",
    "MistralSettings",
    "OcrSettings",
    "Settings",
    "get_settings",
]

#: The OCR model the pipeline calls unless the environment names another.
DEFAULT_OCR_MODEL = "mistral-ocr-latest"


class BookSettings(BaseSettings):
    """Source book location."""

    model_config = group_config("book")

    filename: str = "murphy.pdf"


class ImageSettings(BaseSettings):
    """Page rendering options for the extraction pipeline."""

    model_config = group_config("images")

    pages_dpi: int = 300


class MistralSettings(BaseSettings):
    """Mistral's credentials: the OCR stage is its only caller."""

    model_config = group_config("mistral")

    api_key: SecretStr | None = None


class OcrSettings(BaseSettings):
    """Which Mistral OCR model reads the grammar pages."""

    model_config = group_config("ocr")

    model: str = DEFAULT_OCR_MODEL


class Settings(LLMAppSettings):
    """Everything the pipeline needs to run."""

    book: BookSettings = Field(default_factory=BookSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    ocr: OcrSettings = Field(default_factory=OcrSettings)
    mistral: MistralSettings = Field(default_factory=MistralSettings)

    def missing_required(self) -> list[str]:
        """Return human-readable reasons a full pipeline run cannot finish."""
        problems = super().missing_required()

        if secret_value(self.mistral.api_key) is None:
            problems.append(
                f"{env_var(self.mistral, 'api_key')} is not set "
                "(needed by ocr-grammar-images)"
            )

        source = self.paths.source_dir / self.book.filename
        if not source.exists():
            problems.append(f"the source book is not at {source}")

        return problems


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading env files on first use."""
    return load_settings(Settings)
