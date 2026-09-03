"""Command line interface for the content pipeline.

One command per stage, in the order they run. Every stage is resumable and
writes files, so a run that stops halfway can be continued rather than redone.

The stages that call an LLM share one chat-model client, built here: a client
owns an HTTP connection pool, and the pipeline makes thousands of calls.
"""

import asyncio
from enum import StrEnum
from pathlib import Path

import typer
from langchain_core.language_models.chat_models import BaseChatModel
from practice_core.errors import ContentError
from practice_runtime.errors import ConfigurationError
from practice_runtime.llm import get_llm
from practice_runtime.logging import get_logger, setup_logging
from practice_runtime.settings import BASE_DIR, DATABASE_FILENAME, secret_value

from practice_extraction import populate as populate_module
from practice_extraction import validate as validate_module
from practice_extraction.agents import AnswersAgent, RulesAgent
from practice_extraction.bundle import build_mobile_content
from practice_extraction.constants import (
    END_ANSWER_PAGE,
    END_CONTENT_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    START_CONTENT_PAGE,
    START_UNIT_PAGE,
)
from practice_extraction.extractors import (
    AnswersExtractor,
    ExerciseOrganizer,
    ImageOcrExtractor,
    PDFHandler,
    RulesExtractor,
)
from practice_extraction.settings import Settings, get_settings
from practice_extraction.stages import STAGE_BY_NAME, STAGES

logger = get_logger(__name__)

app = typer.Typer(help="english-practice content pipeline", no_args_is_help=True)

# Where `packages/app/pyproject.toml` expects the bundled database. The name
# comes from the runtime settings that declare it, not from a fourth literal.
MOBILE_CONTENT_PATH = (
    BASE_DIR / "packages" / "app" / "src" / "practice_app" / "content"
) / DATABASE_FILENAME


def _chat_model() -> BaseChatModel:
    """Build the one chat-model client an extraction run uses.

    Returns:
        A client for the configured provider.

    Raises:
        Exit: With code 1 when the provider has no API key.
    """
    try:
        return get_llm(get_settings().llm)
    except ConfigurationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


def _ready(name: str) -> Settings:
    """Return the settings, refusing to run a stage whose inputs are absent.

    A stage that runs without its inputs does not fail loudly. The rules
    extractor read a missing file, got an empty mapping, spent an LLM call per
    exercise on prompts with no answers in them, and cached every unit it
    ruined -- so the useful moment to stop is before the first call.

    Args:
        name: The stage about to run.

    Returns:
        The settings, when the stage can run.

    Raises:
        Exit: With code 1, listing what is missing and which stage makes it.
    """
    settings = get_settings()
    missing = STAGE_BY_NAME[name].missing_inputs(settings)
    if missing:
        typer.secho(f"{name} cannot run yet:", fg=typer.colors.RED)
        for problem in missing:
            typer.echo(f"  - {problem}")
        raise typer.Exit(code=1)
    return settings


@app.callback()
def prepare(ctx: typer.Context) -> None:
    """Configure logging and create the directories the pipeline writes into."""
    if ctx.invoked_subcommand is None:
        return
    settings = get_settings()
    setup_logging(settings.logging, json_logs=settings.app.is_production)
    settings.paths.create_directories()


class SectionType(StrEnum):
    """A cuttable section of the source book."""

    contents = "contents"
    units = "units"
    answers = "answers"


@app.command()
def check() -> None:
    """Report what a full pipeline run is still missing, stage by stage.

    Raises:
        Exit: With code 1 when something required is missing.
    """
    settings = get_settings()
    problems = settings.missing_required()
    if problems:
        typer.secho("A full run is not possible yet:", fg=typer.colors.RED)
        for problem in problems:
            typer.echo(f"  - {problem}")
    else:
        typer.secho("Configuration looks good.", fg=typer.colors.GREEN)

    # Printed either way. Which stages can run is the more useful half of the
    # answer, and it was unreachable while a missing API key returned first.
    typer.echo("")
    typer.echo("Stages:")
    for stage in STAGES:
        # What a stage produced is checked before what it needs: a finished
        # stage stays finished even once its inputs have been cleared away.
        if stage.writes and stage.is_done(settings):
            typer.secho(f"  {stage.name}: done", fg=typer.colors.GREEN)
            continue
        missing = stage.missing_inputs(settings)
        if missing:
            typer.secho(f"  {stage.name}: waiting", fg=typer.colors.YELLOW)
            for problem in missing:
                typer.echo(f"      - {problem}")
        else:
            typer.secho(f"  {stage.name}: ready", fg=typer.colors.CYAN)

    if problems:
        raise typer.Exit(code=1)


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
    settings = _ready("cut-pdf")
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
    settings = _ready("separate-page-images")
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
    settings = _ready("ocr-grammar-images")
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
    settings = _ready("organize-exercises")
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
    extractor = AnswersExtractor(
        _ready("extract-answers").paths, AnswersAgent(_chat_model())
    )
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
    extractor = RulesExtractor(_ready("extract-rules").paths, RulesAgent(_chat_model()))
    output_path = asyncio.run(extractor.extract())
    logger.info("rules_extracted", output_path=str(output_path))


@app.command()
def populate(
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete an existing database and rebuild it from scratch.",
    ),
) -> None:
    """Build the exercise database from everything the stages extracted.

    Raises:
        Exit: With the script's own exit code when the import fails.
    """
    code = populate_module.main(force=force, paths=_ready("populate").paths)
    if code:
        raise typer.Exit(code=code)


@app.command()
def validate() -> None:
    """Check the exercise database for missing and inconsistent rows.

    Raises:
        Exit: With code 1 when the database has errors.
    """
    code = validate_module.main(_ready("validate").paths.database_path)
    if code:
        raise typer.Exit(code=code)


@app.command()
def bundle(
    output: Path = typer.Option(
        MOBILE_CONTENT_PATH,
        "--output",
        "-o",
        help="Where to write the packaged database.",
    ),
    source: Path | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Database to read. Defaults to the configured one.",
    ),
) -> None:
    """Build the compact exercise database that ships inside the Android app.

    The bot's database is mostly 300-DPI PNG crops; this rewrites them as WebP
    at phone resolution, which is roughly a tenth of the size.

    Raises:
        Exit: With code 1 when the source database is missing.
    """
    db_path = source or get_settings().paths.database_path
    typer.echo(f"Reading {db_path}")

    try:
        result = build_mobile_content(db_path, output, progress=typer.echo)
    except ContentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(result.summary(), fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
