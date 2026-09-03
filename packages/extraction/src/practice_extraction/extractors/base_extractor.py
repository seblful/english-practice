"""Base extractor class with shared functionality."""

import json
from pathlib import Path
from typing import Any, ClassVar, TypeVar

from practice_runtime.errors import ConfigurationError
from practice_runtime.logging import get_logger
from practice_runtime.settings import PathSettings
from pydantic import BaseModel
from tqdm import tqdm

from practice_extraction.models import ExtractedUnitsRoot

# Both names come from `practice_extraction.stages`, the one place the
# pipeline's filenames are written: they used to be re-declared as literals
# here and again in the importer.
from practice_extraction.stages import SOURCE_ANSWERS_FILENAME, TOPIC_MAP_FILENAME

RootT = TypeVar("RootT", bound=ExtractedUnitsRoot[Any])

# Exercise ids are "<unit>.<number>", so they split into exactly two parts.
_EXERCISE_ID_PARTS = 2

logger = get_logger(__name__)


class BaseExtractor:
    """Base class for extractors with shared functionality.

    A subclass names the file it writes with :attr:`OUTPUT_FILENAME` and
    overrides :meth:`_process_unit`. Everything else — where the source units,
    the exercise images and the topic map live — comes from the one
    :class:`~practice_runtime.settings.PathSettings` the caller passes in, so a
    stage cannot be wired to a directory the rest of the application does not
    use.
    """

    OUTPUT_FILENAME: ClassVar[str] = ""

    def __init__(self, paths: PathSettings) -> None:
        """Initialize the base extractor.

        Args:
            paths: The application's filesystem layout.

        Raises:
            ConfigurationError: If the subclass names no output file.
        """
        if not self.OUTPUT_FILENAME:
            raise ConfigurationError(
                f"{type(self).__name__} does not declare an OUTPUT_FILENAME"
            )
        self._paths = paths
        self._output_path = paths.metadata_dir / self.OUTPUT_FILENAME
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

    def _get_topic_name(self, unit_id: str) -> str:
        """Get topic name for a unit."""
        return self._unit_topic_map.get(unit_id, "Unknown Topic")

    def _get_image_path(self, exercise_id: str) -> Path | None:
        """Get the image path for an exercise."""
        parts = exercise_id.split(".")
        if len(parts) != _EXERCISE_ID_PARTS:
            return None

        path = self._paths.exercises_dir / parts[0] / f"{exercise_id}.png"
        return path if path.exists() else None

    def _load_answers_data(self) -> dict:
        """Load answers data from JSON file."""
        if not self._answers_path.exists():
            return {}
        return json.loads(self._answers_path.read_text(encoding="utf-8"))

    def _load_output(self, output_model: type[RootT]) -> RootT:
        """Load existing output or return empty model."""
        if self._output_path.exists():
            return output_model.model_validate_json(
                self._output_path.read_text(encoding="utf-8")
            )
        return output_model()

    def _save_output(self, output: ExtractedUnitsRoot[Any]) -> None:
        """Save output incrementally."""
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    def _is_unit_processed(self, output: ExtractedUnitsRoot[Any], unit_id: str) -> bool:
        """Check if unit was already processed."""
        return any(u.unit_id == unit_id for u in output.units)

    @staticmethod
    def _warn_if_hollow(unit_id: str, unit_data: Any) -> None:
        """Say so when a unit came back with nothing in it.

        A unit is cached by its presence in the output, so one whose calls all
        came back unusable is skipped on every re-run from then on. Whether
        that is worth re-running is the operator's call -- but it has to be
        visible when it happens, rather than surfacing three stages later as
        `validate`'s "Questions without answers" count.

        Args:
            unit_id: The unit just processed.
            unit_data: What the subclass built for it.
        """
        exercises = getattr(unit_data, "exercises", [])
        questions = sum(len(getattr(e, "questions", [])) for e in exercises)
        if questions:
            return
        logger.warning(
            "unit_extracted_empty",
            unit_id=unit_id,
            exercises=len(exercises),
        )

    async def _extract_units(self, output_model: type[RootT]) -> Path:
        """Extract data from all units, resuming past ones already processed.

        Args:
            output_model: The output model class to use.

        Returns:
            The file the extraction was written to.
        """
        data = self._load_answers_data()
        output = self._load_output(output_model)

        for unit in tqdm(data.get("units", []), desc="Processing units"):
            unit_id = unit["unit_id"]
            if self._is_unit_processed(output, unit_id):
                logger.info("unit_already_processed", unit_id=unit_id)
                continue

            unit_data = await self._process_unit(unit)
            self._warn_if_hollow(unit_id, unit_data)
            output.units.append(unit_data)
            self._save_output(output)

        logger.info("extraction_written", output_path=str(self._output_path))
        return self._output_path

    async def _process_unit(self, unit: dict) -> BaseModel:
        """Process a unit. Override in subclass."""
        raise NotImplementedError
