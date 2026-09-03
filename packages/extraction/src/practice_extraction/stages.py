"""What each pipeline stage reads, what it writes, and therefore its order.

The pipeline is eight programs that talk to each other through the filesystem,
which makes the layout its real interface -- and for a while that interface was
written down only in prose. The order lived in a README, the filenames were
re-declared as string literals in six modules, and nothing checked either. So
``extract-rules`` run before ``extract-answers`` did not stop: it read a file
that was not there, got an empty mapping back, sent 566 exercises to the model
with no answers in the prompt, and then cached every ruined unit so that a
re-run skipped them.

Declaring the inputs and outputs makes that a refusal instead. A stage knows
what it needs, so the command can say what is absent and which stage produces
it, and ``check`` can report the whole run rather than two settings.

The filenames below are the single source of truth for them; the extractors and
the importer read them from here rather than spelling them again.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from practice_extraction.settings import Settings

__all__ = [
    "ANSWERS_FULL_FILENAME",
    "RULES_FILENAME",
    "SOURCE_ANSWERS_FILENAME",
    "STAGES",
    "STAGE_BY_NAME",
    "TOPIC_MAP_FILENAME",
    "UNIT_TITLES_FILENAME",
    "Artifact",
    "Stage",
]

# Brought by hand, not produced by any stage.
SOURCE_ANSWERS_FILENAME = "answers.json"
UNIT_TITLES_FILENAME = "unit_to_title.json"
TOPIC_MAP_FILENAME = "topic_to_unit.json"

# Written by the two LLM stages.
ANSWERS_FULL_FILENAME = "answers_full.json"
RULES_FILENAME = "rules.json"


@dataclass(frozen=True, slots=True)
class Artifact:
    """One thing on disk that a stage reads or writes.

    ``produced_by`` is what makes a missing input actionable: either it names
    the stage to run first, or it is ``None``, which means nothing in this
    pipeline makes it and the operator has to supply it.
    """

    name: str
    locate: Callable[[Settings], Path]
    produced_by: str | None = None

    def path(self, settings: Settings) -> Path:
        """Return where this artifact lives under the configured layout."""
        return self.locate(settings)

    def exists(self, settings: Settings) -> bool:
        """Return whether the artifact is actually there.

        A directory counts only when it holds something. Every stage command
        creates the tree it writes into before it runs, so an empty directory
        is the normal state of an output nobody has produced yet -- treating it
        as present is what let a stage run on nothing.
        """
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
        """Return one line per input that is not there.

        Args:
            settings: The configured layout.

        Returns:
            The absences, in the order the stage reads them; empty when the
            stage can run.
        """
        return [
            artifact.describe_absence(settings)
            for artifact in self.reads
            if not artifact.exists(settings)
        ]

    def is_done(self, settings: Settings) -> bool:
        """Return whether every output this stage produces is there."""
        return all(artifact.exists(settings) for artifact in self.writes)


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

#: Every stage, in the order they run. The order is not declared separately:
#: each stage names the artifacts it needs, and those name the stage that
#: writes them, so this sequence is checkable rather than merely conventional.
STAGES: tuple[Stage, ...] = (
    Stage("cut-pdf", reads=(SOURCE_BOOK,), writes=(SNIPPETS,)),
    Stage(
        "separate-page-images",
        reads=(SOURCE_BOOK,),
        writes=(GRAMMAR_PAGES, EXERCISE_PAGES),
    ),
    Stage("ocr-grammar-images", reads=(GRAMMAR_PAGES,), writes=(GRAMMAR_MD,)),
    Stage("organize-exercises", reads=(EXERCISE_PAGES,), writes=(EXERCISE_CROPS,)),
    Stage(
        "extract-answers",
        reads=(SOURCE_ANSWERS, EXERCISE_CROPS),
        writes=(ANSWERS_FULL,),
    ),
    Stage(
        "extract-rules",
        reads=(SOURCE_ANSWERS, ANSWERS_FULL, GRAMMAR_MD, EXERCISE_CROPS),
        writes=(RULES,),
    ),
    Stage(
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
    ),
    Stage("validate", reads=(DATABASE,)),
    Stage("bundle", reads=(DATABASE,)),
)

STAGE_BY_NAME: dict[str, Stage] = {stage.name: stage for stage in STAGES}
