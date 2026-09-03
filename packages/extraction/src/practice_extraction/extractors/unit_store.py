"""The content tree an extraction stage reads and writes.

Both LLM stages walk the same tree: the book's answer key names the units, the
topic map names their topics, the crops are on disk beside them, and each
stage's own output file is what makes a run resumable.

This used to be a base class the two extractors inherited. Nothing was ever
typed as it, so it was not an interface at a seam -- it was a shared parent
whose declared result (``-> BaseModel``) was weaker than what either subclass
actually returned, which is why it reached for its fields with ``getattr`` and
a default. Held rather than inherited, each stage keeps its own typed result
and the tree keeps its own.
"""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar

from practice_runtime.logging import get_logger
from practice_runtime.settings import PathSettings
from tqdm import tqdm

from practice_extraction.models import ExtractedUnitsRoot

# Both names come from `practice_extraction.stages`, the one place the
# pipeline's filenames are written: they used to be re-declared as literals
# here and again in the importer.
from practice_extraction.stages import SOURCE_ANSWERS_FILENAME, TOPIC_MAP_FILENAME

__all__ = ["ExtractedUnit", "UnitProcessor", "UnitStore"]

RootT = TypeVar("RootT", bound=ExtractedUnitsRoot[Any])


class ExtractedUnit(Protocol):
    """What a stage builds for one unit: exercises, each with questions.

    Named as a protocol rather than left at ``BaseModel``, which is what the
    base class declared -- so weak that counting a unit's questions had to go
    through ``getattr`` with a default and could not have been wrong.
    """

    unit_id: str
    exercises: list[Any]


#: What a stage does with one unit of the book's answer key.
type UnitProcessor[UnitT] = Callable[[dict], Awaitable[UnitT]]

# Exercise ids are "<unit>.<number>", so they split into exactly two parts.
_EXERCISE_ID_PARTS = 2

logger = get_logger(__name__)


class UnitStore:
    """One stage's view of the content tree: what to read, where to write."""

    def __init__(self, paths: PathSettings, output_filename: str) -> None:
        """Initialize the store.

        Args:
            paths: The application's filesystem layout, so a stage cannot be
                wired to a directory the rest of the application does not use.
            output_filename: The file this stage writes, from
                :mod:`practice_extraction.stages`.
        """
        self._paths = paths
        self.output_path = paths.metadata_dir / output_filename
        self._answers_path = paths.metadata_dir / SOURCE_ANSWERS_FILENAME
        self._unit_topic_map = self._load_unit_topic_map()

    def _load_unit_topic_map(self) -> dict[str, str]:
        """Load mapping from unit_id to topic name."""
        topic_to_unit_path = self._paths.metadata_dir / TOPIC_MAP_FILENAME
        if not topic_to_unit_path.exists():
            return {}

        topic_data = json.loads(topic_to_unit_path.read_text(encoding="utf-8"))
        return {
            str(unit_id): item["topic"]
            for item in topic_data
            for unit_id in item["unit_ids"]
        }

    def topic_name(self, unit_id: str) -> str:
        """Return the topic a unit is filed under.

        Args:
            unit_id: The unit to look up.

        Returns:
            Its topic, or a placeholder when the map does not list it.
        """
        return self._unit_topic_map.get(unit_id, "Unknown Topic")

    def image_path(self, exercise_id: str) -> Path | None:
        """Return the crop for one exercise.

        Args:
            exercise_id: The exercise, as ``"<unit>.<number>"``.

        Returns:
            The image, or ``None`` when the id is malformed or the file is
            not there.
        """
        parts = exercise_id.split(".")
        if len(parts) != _EXERCISE_ID_PARTS:
            return None

        path = self._paths.exercises_dir / parts[0] / f"{exercise_id}.png"
        return path if path.exists() else None

    def grammar_markdown(self, unit_number: int) -> str | None:
        """Return the OCR-ed grammar page for a unit.

        Args:
            unit_number: The unit whose page to read.

        Returns:
            Its markdown, or ``None`` when the page was never read.
        """
        path = self._paths.grammar_md_dir / f"{unit_number}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def source_answers(self) -> dict:
        """Return the book's answer key, which names every unit and exercise.

        Returns:
            The decoded file, or an empty mapping when it is not there.
        """
        if not self._answers_path.exists():
            return {}
        return json.loads(self._answers_path.read_text(encoding="utf-8"))

    def load_output(self, output_model: type[RootT]) -> RootT:
        """Return what this stage has written so far.

        Args:
            output_model: The root model to read it as.

        Returns:
            The stored output, or an empty one for a run that has not started.
        """
        if self.output_path.exists():
            return output_model.model_validate_json(
                self.output_path.read_text(encoding="utf-8")
            )
        return output_model()

    def save_output(self, output: ExtractedUnitsRoot[Any]) -> None:
        """Write the output so far, so an interrupted run resumes.

        Args:
            output: Everything extracted up to now.
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    async def extract_units(
        self,
        output_model: type[RootT],
        process: UnitProcessor[Any],
    ) -> Path:
        """Walk every unit that has not been done, and write as it goes.

        Args:
            output_model: The root model this stage writes.
            process: What the stage does with one unit of the answer key.

        Returns:
            The file the extraction was written to.
        """
        data = self.source_answers()
        output = self.load_output(output_model)

        for unit in tqdm(data.get("units", []), desc="Processing units"):
            unit_id = unit["unit_id"]
            if any(u.unit_id == unit_id for u in output.units):
                logger.info("unit_already_processed", unit_id=unit_id)
                continue

            unit_data = await process(unit)
            _warn_if_hollow(unit_id, unit_data)
            output.units.append(unit_data)
            self.save_output(output)

        logger.info("extraction_written", output_path=str(self.output_path))
        return self.output_path


def _warn_if_hollow(unit_id: str, unit_data: ExtractedUnit) -> None:
    """Say so when a unit came back with nothing in it.

    A unit is cached by its presence in the output, so one whose calls all
    came back unusable is skipped on every re-run from then on. Whether that
    is worth re-running is the operator's call -- but it has to be visible
    when it happens, rather than surfacing three stages later as `validate`'s
    "Questions without answers" count.

    Args:
        unit_id: The unit just processed.
        unit_data: What the stage built for it.
    """
    questions = sum(len(exercise.questions) for exercise in unit_data.exercises)
    if questions:
        return
    logger.warning(
        "unit_extracted_empty",
        unit_id=unit_id,
        exercises=len(unit_data.exercises),
    )
