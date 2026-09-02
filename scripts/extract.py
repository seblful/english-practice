import asyncio
import sys
from enum import StrEnum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from english_practice.extractors import (
    AnswersExtractor,
    ExerciseOrganizer,
    ImageOcrExtractor,
    PDFHandler,
    RulesExtractor,
)
from english_practice.logging import get_logger
from english_practice.models.constants import (
    END_ANSWER_PAGE,
    END_CONTENT_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    START_CONTENT_PAGE,
    START_UNIT_PAGE,
)
from english_practice.settings import get_settings, secret_value

logger = get_logger(__name__)

app = typer.Typer()

# This is a script entry point, so reading settings at import time is fine; the
# library modules all go through get_settings() at call time instead.
settings = get_settings()


@app.callback()
def prepare() -> None:
    """Create the source and content directories the pipeline writes into."""
    settings.paths.create_directories()


class SectionType(StrEnum):
    """A cuttable section of the source book."""

    contents = "contents"
    units = "units"
    answers = "answers"


@app.command(
    name="cut-pdf",
    help="Cut a PDF file based on the section type provided.",
)
def cut_pdf(
    section: SectionType = typer.Argument(
        ..., help="The section of the book to cut (contents, units, answers)."
    ),
) -> None:
    """Cut the given section out of the source PDF."""
    page_ranges = {
        SectionType.contents: (START_CONTENT_PAGE, END_CONTENT_PAGE),
        SectionType.units: (START_UNIT_PAGE, END_UNIT_PAGE),
        SectionType.answers: (START_ANSWER_PAGE, END_ANSWER_PAGE),
    }

    start_page, end_page = page_ranges[section]

    logger.info(
        "pdf_section_cutting",
        section=section.value,
        start_page=start_page,
        end_page=end_page,
    )

    handler = PDFHandler()
    output_path = settings.paths.snippets_dir / f"{section.value}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handler.cut_pdf(
        file_path=settings.paths.source_dir / settings.book.filename,
        start_page=start_page,
        end_page=end_page,
        output_path=output_path,
    )


@app.command(
    name="separate-page-images",
    help="Separate pages from a PDF file into grammar pages and exercise pages.",
)
def separate_page_images() -> None:
    """Split unit pages into grammar and exercise images."""
    handler = PDFHandler()
    handler.separate_page_images(
        file_path=settings.paths.source_dir / settings.book.filename,
        start_page=START_UNIT_PAGE,
        end_page=END_UNIT_PAGE,
        grammar_pages_dir=settings.paths.grammar_pages_dir,
        exercises_pages_dir=settings.paths.exercises_pages_dir,
        dpi=settings.images.pages_dpi,
    )


@app.command(
    name="ocr-grammar-images",
    help=(
        "Extract text from grammar page images via OCR "
        "and save to data/grammar (resumable)."
    ),
)
def ocr_grammar_images() -> None:
    """Run OCR on grammar page images; save .md to data/grammar. Skips existing."""
    extractor = ImageOcrExtractor(
        api_key=secret_value(settings.ocr.api_key),
        model=settings.ocr.model,
    )
    settings.paths.grammar_md_dir.mkdir(parents=True, exist_ok=True)
    written = extractor.ocr_dir(
        settings.paths.grammar_pages_dir,
        output_dir=settings.paths.grammar_md_dir,
    )
    logger.info(
        "grammar_pages_ocred",
        count=len(written),
        output_dir=str(settings.paths.grammar_md_dir),
    )


@app.command(
    name="organize-exercises",
    help="Organize exercise images into numbered folders.",
)
def organize_exercises() -> None:
    """Organize exercise images into separate folders."""
    organizer = ExerciseOrganizer()
    created = organizer.organize(
        file_path=settings.paths.exercises_pages_dir,
        output_dir=settings.paths.exercises_dir,
    )
    logger.info(
        "exercises_organized",
        count=len(created),
        output_dir=str(settings.paths.exercises_dir),
    )


@app.command(
    name="extract-answers",
    help="Extract answers from exercise images using LLM.",
)
def extract_answers() -> None:
    """Extract answers from exercise images using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to answers_full.json. Resumes from last stopped unit.
    """
    extractor = AnswersExtractor(settings.paths)
    output_path = asyncio.run(extractor.extract())
    logger.info("answers_extracted", output_path=str(output_path))


@app.command(
    name="extract-rules",
    help="Extract grammar rules from exercises using LLM.",
)
def extract_rules() -> None:
    """Extract grammar rules from exercises using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to rules.json. Resumes from last stopped unit.
    """
    extractor = RulesExtractor(settings.paths)
    output_path = asyncio.run(extractor.extract())
    logger.info("rules_extracted", output_path=str(output_path))


if __name__ == "__main__":
    app()
