"""Tests for the extraction pipeline CLI.

Each command is wiring: it reads the configured layout, builds one collaborator
and calls it. These tests assert the wiring, with the collaborators mocked --
the extractors themselves are covered by their own tests.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from english_practice.models.constants import (
    END_ANSWER_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    START_UNIT_PAGE,
)
from english_practice.settings import Settings
from scripts import extract
from tests.conftest import extraction_paths

runner = CliRunner()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point the CLI at a temporary layout instead of the real ``data/``."""
    settings = Settings(paths=extraction_paths(tmp_path))
    settings.paths.source_dir = tmp_path / "source"
    settings.paths.grammar_pages_dir = tmp_path / "source" / "grammar"
    settings.paths.exercises_pages_dir = tmp_path / "source" / "exercises"
    settings.paths.snippets_dir = tmp_path / "source" / "snippets"
    monkeypatch.setattr(extract, "settings", settings)
    return settings


def _invoke(*args: str) -> None:
    """Run one CLI command, failing the test if it exits non-zero."""
    result = runner.invoke(extract.app, list(args))
    assert result.exit_code == 0, result.output


class TestCutPdf:
    """The book is cut into the sections the operator works from by hand."""

    @pytest.mark.parametrize(
        ("section", "pages"),
        [
            ("units", (START_UNIT_PAGE, END_UNIT_PAGE)),
            ("answers", (START_ANSWER_PAGE, END_ANSWER_PAGE)),
        ],
        ids=["units", "answers"],
    )
    def test_cuts_the_named_section(
        self, settings: Settings, section: str, pages: tuple[int, int]
    ) -> None:
        with patch.object(extract, "PDFHandler") as handler:
            _invoke("cut-pdf", section)

        call = handler.return_value.cut_pdf.call_args.kwargs
        assert (call["start_page"], call["end_page"]) == pages
        assert call["output_path"] == settings.paths.snippets_dir / f"{section}.pdf"

    def test_rejects_a_section_the_book_has_no_pages_for(self) -> None:
        result = runner.invoke(extract.app, ["cut-pdf", "index"])

        assert result.exit_code != 0


class TestSeparatePageImages:
    """Tests for splitting unit pages into grammar and exercise images."""

    def test_passes_the_unit_page_range_and_dpi(self, settings: Settings) -> None:
        with patch.object(extract, "PDFHandler") as handler:
            _invoke("separate-page-images")

        call = handler.return_value.separate_page_images.call_args.kwargs
        assert (call["start_page"], call["end_page"]) == (
            START_UNIT_PAGE,
            END_UNIT_PAGE,
        )
        assert call["dpi"] == settings.images.pages_dpi
        assert call["grammar_pages_dir"] == settings.paths.grammar_pages_dir


class TestOcrGrammarImages:
    """Tests for OCR-ing the grammar pages."""

    def test_reads_the_pages_and_writes_the_markdown(self, settings: Settings) -> None:
        with patch.object(extract, "ImageOcrExtractor") as ocr:
            ocr.return_value.ocr_dir.return_value = [Path("1.md")]
            _invoke("ocr-grammar-images")

        assert ocr.call_args.kwargs["model"] == settings.ocr.model
        call = ocr.return_value.ocr_dir.call_args
        assert call.args[0] == settings.paths.grammar_pages_dir
        assert call.kwargs["output_dir"] == settings.paths.grammar_md_dir


class TestOrganizeExercises:
    """Tests for slicing page images into per-exercise images."""

    def test_reads_the_page_images_and_writes_the_exercises(
        self, settings: Settings
    ) -> None:
        with patch.object(extract, "ExerciseOrganizer") as organizer:
            organizer.return_value.organize.return_value = [Path("1.1.png")]
            _invoke("organize-exercises")

        call = organizer.return_value.organize.call_args.kwargs
        assert call["file_path"] == settings.paths.exercises_pages_dir
        assert call["output_dir"] == settings.paths.exercises_dir


class TestLlmStages:
    """The two LLM stages take the layout and report the file they wrote."""

    def test_extract_answers_hands_over_the_paths(self, settings: Settings) -> None:
        with patch.object(extract, "AnswersExtractor") as extractor:
            extractor.return_value.extract = MagicMock(
                return_value=_awaitable(Path("answers_full.json"))
            )
            _invoke("extract-answers")

        assert extractor.call_args.args[0] is settings.paths

    def test_extract_rules_hands_over_the_paths(self, settings: Settings) -> None:
        with patch.object(extract, "RulesExtractor") as extractor:
            extractor.return_value.extract = MagicMock(
                return_value=_awaitable(Path("rules.json"))
            )
            _invoke("extract-rules")

        assert extractor.call_args.args[0] is settings.paths


def _awaitable(value: object):
    """Return a coroutine yielding ``value``, for ``asyncio.run`` to drive."""

    async def _coro() -> object:
        return value

    return _coro()
