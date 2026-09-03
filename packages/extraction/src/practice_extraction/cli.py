"""Command line interface for the content pipeline.

One command per stage, in the order they run. Every stage is resumable and
writes files, so a run that stops halfway can be continued rather than redone.

The stages that call an LLM share one chat-model client, built here: a client
owns an HTTP connection pool, and the pipeline makes thousands of calls.
"""

import asyncio
import functools
import inspect
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from langchain_core.language_models.chat_models import BaseChatModel
from practice_core.errors import ContentError
from practice_runtime.errors import ConfigurationError
from practice_runtime.llm import get_llm
from practice_runtime.logging import get_logger, setup_logging
from practice_runtime.settings import secret_value

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
from practice_extraction.stages import (
    BUNDLE,
    CUT_PDF,
    EXTRACT_ANSWERS,
    EXTRACT_RULES,
    MOBILE_CONTENT_PATH,
    OCR_GRAMMAR_IMAGES,
    ORGANIZE_EXERCISES,
    POPULATE,
    SEPARATE_PAGE_IMAGES,
    STAGES,
    VALIDATE,
    Stage,
    StageRunner,
    register,
)

logger = get_logger(__name__)

app = typer.Typer(help="english-practice content pipeline", no_args_is_help=True)


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


def _ready(stage: Stage) -> Settings:
    """Return the settings, refusing to run a stage whose inputs are absent.

    A stage that runs without its inputs does not fail loudly. The rules
    extractor read a missing file, got an empty mapping, spent an LLM call per
    exercise on prompts with no answers in them, and cached every unit it
    ruined -- so the useful moment to stop is before the first call.

    Args:
        stage: The stage about to run.

    Returns:
        The settings, when the stage can run.

    Raises:
        Exit: With code 1, listing what is missing and which stage makes it.
    """
    settings = get_settings()
    missing = stage.missing_inputs(settings)
    if missing:
        typer.secho(f"{stage.name} cannot run yet:", fg=typer.colors.RED)
        for problem in missing:
            typer.echo(f"  - {problem}")
        raise typer.Exit(code=1)
    return settings


def stage_command(
    stage: Stage, **command_kwargs: Any
) -> Callable[[StageRunner], StageRunner]:
    """Bind one function to one stage: its runner, and its command.

    The stage supplies the command's name and the gate its inputs are checked
    against, so the two halves cannot drift. They used to be joined by a
    string typed twice -- once in ``@app.command(name=...)``, once in the
    ``_ready("...")`` call inside the body -- with nothing checking that a
    stage had a command at all. ``bundle`` did not call the gate, and its
    declared input was enforced only by ``check``.

    The command's parameters are the runner's own, minus the settings it is
    handed, so a stage that takes an option declares it once.

    Args:
        stage: The stage this function performs.
        command_kwargs: Passed to typer, for the help text.

    Returns:
        A decorator that registers the runner and returns it unchanged.
    """

    def bind(runner: StageRunner) -> StageRunner:
        register(stage, runner)
        signature = inspect.signature(runner)

        @functools.wraps(runner)
        def command(*args: Any, **kwargs: Any) -> None:
            code = stage.run(_ready(stage), *args, **kwargs)
            if code:
                raise typer.Exit(code=code)

        # Typer reads the callback's signature to build the command's
        # options, so the runner's own parameters are handed over minus the
        # settings it is given: a stage that takes an option declares it once.
        visible = signature.replace(
            parameters=[
                parameter
                for name, parameter in signature.parameters.items()
                if name != "settings"
            ],
            return_annotation=None,
        )
        setattr(command, "__signature__", visible)  # noqa: B010
        app.command(name=stage.name, **command_kwargs)(command)
        return runner

    return bind


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


@stage_command(CUT_PDF, help="Cut a PDF file based on the section type provided.")
def cut_pdf(
    settings: Settings,
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


@stage_command(
    SEPARATE_PAGE_IMAGES,
    help="Separate pages from a PDF file into grammar pages and exercise pages.",
)
def separate_page_images(settings: Settings) -> None:
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


@stage_command(
    OCR_GRAMMAR_IMAGES,
    help=(
        "Extract text from grammar page images via OCR "
        "and save to data/grammar (resumable)."
    ),
)
def ocr_grammar_images(settings: Settings) -> None:
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


@stage_command(
    ORGANIZE_EXERCISES, help="Organize exercise images into numbered folders."
)
def organize_exercises(settings: Settings) -> None:
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


@stage_command(EXTRACT_ANSWERS, help="Extract answers from exercise images using LLM.")
def extract_answers(settings: Settings) -> None:
    """Extract answers from exercise images using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to answers_full.json. Resumes from last stopped unit.
    """
    extractor = AnswersExtractor(settings.paths, AnswersAgent(_chat_model()))
    output_path = asyncio.run(extractor.extract())
    logger.info("answers_extracted", output_path=str(output_path))


@stage_command(EXTRACT_RULES, help="Extract grammar rules from exercises using LLM.")
def extract_rules(settings: Settings) -> None:
    """Extract grammar rules from exercises using LLM.

    Processes all questions per exercise in a single LLM call.
    Outputs to rules.json. Resumes from last stopped unit.
    """
    extractor = RulesExtractor(settings.paths, RulesAgent(_chat_model()))
    output_path = asyncio.run(extractor.extract())
    logger.info("rules_extracted", output_path=str(output_path))


@stage_command(
    POPULATE,
    help="Build the exercise database from everything the stages extracted.",
)
def populate(
    settings: Settings,
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete an existing database and rebuild it from scratch.",
    ),
) -> int:
    """Build the exercise database from everything the stages extracted.

    Returns:
        The importer's exit code.
    """
    return populate_module.main(force=force, paths=settings.paths)


@stage_command(
    VALIDATE, help="Check the exercise database for missing and inconsistent rows."
)
def validate(settings: Settings) -> int:
    """Check the exercise database for missing and inconsistent rows.

    Returns:
        The report's exit code, non-zero when the database has errors.
    """
    return validate_module.main(settings.paths.database_path)


@stage_command(
    BUNDLE,
    help="Build the compact exercise database that ships inside the Android app.",
)
def bundle(
    settings: Settings,
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
    db_path = source or settings.paths.database_path
    typer.echo(f"Reading {db_path}")

    try:
        result = build_mobile_content(db_path, output, progress=typer.echo)
    except ContentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(result.summary(), fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
