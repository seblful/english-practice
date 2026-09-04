"""What each pipeline stage reads, what it writes, and therefore its order."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from practice_runtime.errors import ConfigurationError
from practice_runtime.settings import BASE_DIR, DATABASE_FILENAME

from practice_extraction.settings import Settings

__all__ = [
    "ANSWERS_FULL_FILENAME",
    "MOBILE_CONTENT_PATH",
    "RULES_FILENAME",
    "SOURCE_ANSWERS_FILENAME",
    "STAGES",
    "STAGE_BY_NAME",
    "TOPIC_MAP_FILENAME",
    "UNIT_TITLES_FILENAME",
    "Artifact",
    "Stage",
    "StageRunner",
    "register",
]

#: Where `packages/app/pyproject.toml` expects the bundled database.
MOBILE_CONTENT_PATH = (
    BASE_DIR / "packages" / "app" / "src" / "practice_app" / "content"
) / DATABASE_FILENAME

# Brought by hand, not produced by any stage.
SOURCE_ANSWERS_FILENAME = "answers.json"
UNIT_TITLES_FILENAME = "unit_to_title.json"
TOPIC_MAP_FILENAME = "topic_to_unit.json"

# Written by the two LLM stages.
ANSWERS_FULL_FILENAME = "answers_full.json"
RULES_FILENAME = "rules.json"


@dataclass(frozen=True, slots=True)
class Artifact:
    """One thing on disk that a stage reads or writes."""

    name: str
    locate: Callable[[Settings], Path]
    produced_by: str | None = None

    def path(self, settings: Settings) -> Path:
        """Return where this artifact lives under the configured layout."""
        return self.locate(settings)

    def exists(self, settings: Settings) -> bool:
        """Return whether the artifact is actually there."""
        path = self.path(settings)
        if path.is_dir():
            return any(path.iterdir())
        return path.is_file()

    def describe_absence(self, settings: Settings) -> str:
        """Return a line saying what is missing and how to get it."""
        remedy = (
            f"run: practice-content {self.produced_by}"
            if self.produced_by is not None
            else "supply it by hand"
        )
        return f"{self.name} is not at {self.path(settings)} ({remedy})"


@dataclass(frozen=True, slots=True)
class Stage:
    """One command of the pipeline, and the files on either side of it."""

    name: str
    reads: tuple[Artifact, ...] = field(default_factory=tuple)
    writes: tuple[Artifact, ...] = field(default_factory=tuple)

    def missing_inputs(self, settings: Settings) -> list[str]:
        """Return one line per input that is not there."""
        return [
            artifact.describe_absence(settings)
            for artifact in self.reads
            if not artifact.exists(settings)
        ]

    def is_done(self, settings: Settings) -> bool:
        """Return whether every output this stage produces is there."""
        return all(artifact.exists(settings) for artifact in self.writes)

    @property
    def runner(self) -> "StageRunner | None":
        """Return what this stage does, once something has declared it."""
        return _RUNNERS.get(self.name)

    def run(self, settings: Settings, *args: Any, **kwargs: Any) -> int:
        """Do this stage's work."""
        runner = self.runner
        if runner is None:
            raise ConfigurationError(f"no runner is declared for {self.name}")
        return runner(settings, *args, **kwargs) or 0


#: What each stage does, filled in by :func:`register`; the runners are heavy.
_RUNNERS: dict[str, "StageRunner"] = {}

#: A stage's work: the settings, its command's own options, and an exit code.
type StageRunner = Callable[..., int | None]


def register(stage: Stage, runner: StageRunner) -> None:
    """Declare what a stage does."""
    if stage.name in _RUNNERS:
        raise ConfigurationError(f"{stage.name} already has a runner")
    _RUNNERS[stage.name] = runner


SOURCE_BOOK = Artifact(
    "the source book",
    lambda s: s.paths.source_dir / s.book.filename,
)
SNIPPETS = Artifact(
    "the cut PDF sections",
    lambda s: s.paths.snippets_dir,
    produced_by="cut-pdf",
)
GRAMMAR_PAGES = Artifact(
    "the rendered grammar pages",
    lambda s: s.paths.grammar_pages_dir,
    produced_by="separate-page-images",
)
EXERCISE_PAGES = Artifact(
    "the rendered exercise pages",
    lambda s: s.paths.exercises_pages_dir,
    produced_by="separate-page-images",
)
GRAMMAR_MD = Artifact(
    "the OCR-ed grammar markdown",
    lambda s: s.paths.grammar_md_dir,
    produced_by="ocr-grammar-images",
)
EXERCISE_CROPS = Artifact(
    "the cropped exercise images",
    lambda s: s.paths.exercises_dir,
    produced_by="organize-exercises",
)
SOURCE_ANSWERS = Artifact(
    "the book's answer key",
    lambda s: s.paths.metadata_dir / SOURCE_ANSWERS_FILENAME,
)
UNIT_TITLES = Artifact(
    "the unit titles",
    lambda s: s.paths.metadata_dir / UNIT_TITLES_FILENAME,
)
TOPIC_MAP = Artifact(
    "the topic-to-unit map",
    lambda s: s.paths.metadata_dir / TOPIC_MAP_FILENAME,
)
ANSWERS_FULL = Artifact(
    "the extracted answers",
    lambda s: s.paths.metadata_dir / ANSWERS_FULL_FILENAME,
    produced_by="extract-answers",
)
RULES = Artifact(
    "the extracted rules",
    lambda s: s.paths.metadata_dir / RULES_FILENAME,
    produced_by="extract-rules",
)
DATABASE = Artifact(
    "the content database",
    lambda s: s.paths.database_path,
    produced_by="populate",
)
MOBILE_CONTENT = Artifact(
    "the database bundled into the app",
    lambda _: MOBILE_CONTENT_PATH,
    produced_by="bundle",
)

CUT_PDF = Stage("cut-pdf", reads=(SOURCE_BOOK,), writes=(SNIPPETS,))
SEPARATE_PAGE_IMAGES = Stage(
    "separate-page-images",
    reads=(SOURCE_BOOK,),
    writes=(GRAMMAR_PAGES, EXERCISE_PAGES),
)
OCR_GRAMMAR_IMAGES = Stage(
    "ocr-grammar-images", reads=(GRAMMAR_PAGES,), writes=(GRAMMAR_MD,)
)
ORGANIZE_EXERCISES = Stage(
    "organize-exercises", reads=(EXERCISE_PAGES,), writes=(EXERCISE_CROPS,)
)
EXTRACT_ANSWERS = Stage(
    "extract-answers",
    reads=(SOURCE_ANSWERS, EXERCISE_CROPS),
    writes=(ANSWERS_FULL,),
)
EXTRACT_RULES = Stage(
    "extract-rules",
    reads=(SOURCE_ANSWERS, ANSWERS_FULL, GRAMMAR_MD, EXERCISE_CROPS),
    writes=(RULES,),
)
POPULATE = Stage(
    "populate",
    reads=(
        UNIT_TITLES,
        TOPIC_MAP,
        ANSWERS_FULL,
        RULES,
        GRAMMAR_MD,
        EXERCISE_CROPS,
    ),
    writes=(DATABASE,),
)
VALIDATE = Stage("validate", reads=(DATABASE,))
BUNDLE = Stage("bundle", reads=(DATABASE,), writes=(MOBILE_CONTENT,))

#: Every stage, in the order they run -- checkable, since each names its inputs.
STAGES: tuple[Stage, ...] = (
    CUT_PDF,
    SEPARATE_PAGE_IMAGES,
    OCR_GRAMMAR_IMAGES,
    ORGANIZE_EXERCISES,
    EXTRACT_ANSWERS,
    EXTRACT_RULES,
    POPULATE,
    VALIDATE,
    BUNDLE,
)

STAGE_BY_NAME: dict[str, Stage] = {stage.name: stage for stage in STAGES}
