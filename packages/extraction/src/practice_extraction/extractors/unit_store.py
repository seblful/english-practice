"""The content tree an extraction stage reads and writes."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar

from practice_runtime.logging import get_logger
from practice_runtime.settings import PathSettings
from tqdm import tqdm

from practice_extraction.models import ExtractedUnitsRoot

# Both names come from `practice_extraction.stages`, not literals here.
from practice_extraction.stages import SOURCE_ANSWERS_FILENAME, TOPIC_MAP_FILENAME

__all__ = ["ExtractedUnit", "UnitProcessor", "UnitStore"]

RootT = TypeVar("RootT", bound=ExtractedUnitsRoot[Any])


class ExtractedUnit(Protocol):
    """What a stage builds for one unit: exercises, each with questions."""

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
        """Initialize the store."""
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
        """Return the topic a unit is filed under."""
        return self._unit_topic_map.get(unit_id, "Unknown Topic")

    def image_path(self, exercise_id: str) -> Path | None:
        """Return the crop for one exercise."""
        parts = exercise_id.split(".")
        if len(parts) != _EXERCISE_ID_PARTS:
            return None

        path = self._paths.exercises_dir / parts[0] / f"{exercise_id}.png"
        return path if path.exists() else None

    def grammar_markdown(self, unit_number: int) -> str | None:
        """Return the OCR-ed grammar page for a unit."""
        path = self._paths.grammar_md_dir / f"{unit_number}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def source_answers(self) -> dict:
        """Return the book's answer key, which names every unit and exercise."""
        if not self._answers_path.exists():
            return {}
        return json.loads(self._answers_path.read_text(encoding="utf-8"))

    def load_output(self, output_model: type[RootT]) -> RootT:
        """Return what this stage has written so far."""
        if self.output_path.exists():
            return output_model.model_validate_json(
                self.output_path.read_text(encoding="utf-8")
            )
        return output_model()

    def save_output(self, output: ExtractedUnitsRoot[Any]) -> None:
        """Write the output so far, so an interrupted run resumes."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    async def extract_units(
        self,
        output_model: type[RootT],
        process: UnitProcessor[Any],
    ) -> Path:
        """Walk every unit that has not been done, and write as it goes."""
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
    """Say so when a unit came back with nothing in it."""
    questions = sum(len(exercise.questions) for exercise in unit_data.exercises)
    if questions:
        return
    logger.warning(
        "unit_extracted_empty",
        unit_id=unit_id,
        exercises=len(unit_data.exercises),
    )
