import sys
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from config.logging import get_logger
from config.settings import settings
from english_practice.extractors import (
    AnswersExtractor,
    ExerciseOrganizer,
    ImageOcrExtractor,
    PDFHandler,
    RulesExtractor,
)
from english_practice.models.constants import (
    END_ANSWER_PAGE,
    END_CONTENT_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    START_CONTENT_PAGE,
    START_UNIT_PAGE,
)

logger = get_logger(__name__)

app = typer.Typer()


class SectionType(str, Enum):
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

    page_ranges = {
        SectionType.contents: (START_CONTENT_PAGE, END_CONTENT_PAGE),
        SectionType.units: (START_UNIT_PAGE, END_UNIT_PAGE),
        SectionType.answers: (START_ANSWER_PAGE, END_ANSWER_PAGE),
    }

    start_page, end_page = page_ranges[section]

    logger.info(
        f"Cutting PDF for section '{section.value}': Pages {start_page} to {end_page}"
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
    help="Extract text from grammar page images via OCR and save to data/grammar (resumable).",
)
def ocr_grammar_images() -> None:
    """Run OCR on grammar page images; save .md to data/grammar. Skips existing."""
    extractor = ImageOcrExtractor(
        api_key=settings.ocr.api_key,
        model=settings.ocr.model,
    )
    settings.paths.grammar_md_dir.mkdir(parents=True, exist_ok=True)
    written = extractor.ocr_dir(
        settings.paths.grammar_pages_dir,
        output_dir=settings.paths.grammar_md_dir,
    )
    logger.info(
        f"Wrote {len(written)} markdown file(s) to {settings.paths.grammar_md_dir}"
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
    logger.info(f"Organized {len(created)} exercises to {settings.paths.exercises_dir}")


@app.command(
    name="full-answers",
    help="Extract full answers from exercise images using LLM.",
)
async def extract_full_answers(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing answers_full.json"
    ),
) -> None:
    """Extract full answers from exercise images using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to answers_full.json.
    """
    extractor = AnswersExtractor()
    result = await extractor.extract(force=force)
    logger.info(f"Full answers extracted to {result['output_path']}")


@app.command(
    name="rules",
    help="Extract grammar rules from exercises using LLM.",
)
async def extract_rules(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing rules.json"
    ),
) -> None:
    """Extract grammar rules from exercises using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to rules.json.
    """
    extractor = RulesExtractor()
    result = await extractor.extract(force=force)
    logger.info(f"Rules extracted to {result['output_path']}")


if __name__ == "__main__":
    app()
