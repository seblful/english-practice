"""Tests for the pipeline's own settings."""

from pathlib import Path

import pytest
from practice_core.providers import Provider
from practice_runtime.settings import GeminiSettings, LLMSettings, PathSettings
from pydantic import SecretStr

from practice_extraction.settings import (
    DEFAULT_OCR_MODEL,
    MistralSettings,
    OcrSettings,
    Settings,
)


def _runnable(tmp_path: Path) -> Settings:
    """Settings that pass every check, with the book where it is expected."""
    paths = PathSettings(data_dir=tmp_path)
    paths.source_dir.mkdir(parents=True)
    settings = Settings(
        paths=paths,
        gemini=GeminiSettings(api_key=SecretStr("g")),
        mistral=MistralSettings(api_key=SecretStr("m")),
    )
    (paths.source_dir / settings.book.filename).touch()
    return settings


class TestMissingRequired:
    def test_a_runnable_configuration_has_no_problems(self, tmp_path: Path) -> None:
        assert _runnable(tmp_path).missing_required() == []

    def test_reports_a_missing_mistral_key(self, tmp_path: Path) -> None:
        settings = _runnable(tmp_path)
        settings.mistral.api_key = None

        assert settings.missing_required() == [
            "MISTRAL_API_KEY is not set (needed by ocr-grammar-images)"
        ]

    def test_reports_the_chat_models_key(self, tmp_path: Path) -> None:
        settings = _runnable(tmp_path)
        settings.llm = LLMSettings(provider=Provider.OPENROUTER)

        assert settings.missing_required() == [
            "OPENROUTER_API_KEY is not set (LLM_PROVIDER=openrouter)"
        ]

    def test_reports_a_missing_book(self, tmp_path: Path) -> None:
        settings = _runnable(tmp_path)
        settings.book.filename = "absent.pdf"

        assert any("source book" in p for p in settings.missing_required())

    def test_refuses_the_old_ocr_key_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OCR_API_KEY", "m")

        assert _runnable(tmp_path).missing_required() == [
            "OCR_API_KEY is no longer read: rename it to MISTRAL_API_KEY"
        ]


def test_reads_the_mistral_key_and_ocr_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "m")
    monkeypatch.setenv("OCR_MODEL", "mistral-ocr-2")

    assert MistralSettings().api_key == SecretStr("m")
    assert OcrSettings().model == "mistral-ocr-2"


def test_the_ocr_model_has_a_default() -> None:
    assert OcrSettings().model == DEFAULT_OCR_MODEL
