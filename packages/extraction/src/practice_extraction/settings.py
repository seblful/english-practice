"""The pipeline's settings: the shared groups, plus the book and the OCR."""

from functools import lru_cache

from practice_runtime.settings import BaseAppSettings, load_settings, secret_value
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "DEFAULT_OCR_MODEL",
    "BookSettings",
    "ImageSettings",
    "OcrSettings",
    "Settings",
    "get_settings",
]

#: The OCR model the pipeline calls unless the environment names another.
DEFAULT_OCR_MODEL = "mistral-ocr-latest"


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
    model: str = DEFAULT_OCR_MODEL


class Settings(BaseAppSettings):
    """Everything the pipeline needs to run."""

    book: BookSettings = Field(default_factory=BookSettings)
    images: ImageSettings = Field(default_factory=ImageSettings)
    ocr: OcrSettings = Field(default_factory=OcrSettings)

    def missing_required(self) -> list[str]:
        """Return human-readable reasons a full pipeline run cannot finish."""
        problems = super().missing_required()

        if secret_value(self.ocr.api_key) is None:
            problems.append("OCR_API_KEY is not set (needed by ocr-grammar-images)")

        source = self.paths.source_dir / self.book.filename
        if not source.exists():
            problems.append(f"the source book is not at {source}")

        return problems


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loading env files on first use."""
    return load_settings(Settings)
