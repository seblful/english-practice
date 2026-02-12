from enum import Enum

import typer

from config.logging import get_logger
from config.settings import settings
from english_practice.extractors import ImageOcrExtractor, PDFHandler
from english_practice.models import (
    START_CONTENT_PAGE,
    END_CONTENT_PAGE,
    START_UNIT_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    END_ANSWER_PAGE,
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
        file_path=settings.paths.books_dir / settings.book.filename,
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
        file_path=settings.paths.books_dir / settings.book.filename,
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


if __name__ == "__main__":
    app()
