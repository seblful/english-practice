"""Base extractor class with shared functionality."""

import json
from pathlib import Path

from pydantic import BaseModel
from tqdm import tqdm

from config.logging import get_logger

logger = get_logger(__name__)


class BaseExtractor:
    """Base class for extractors with shared functionality."""

    def __init__(
        self,
        output_path: Path,
        answers_path: Path,
        exercises_dir: Path,
        content_dir: Path,
    ) -> None:
        """Initialize the base extractor."""
        self._output_path = output_path
        self._answers_path = answers_path
        self._exercises_dir = exercises_dir
        self._content_dir = content_dir
        self._unit_topic_map = self._load_unit_topic_map()

    def _load_unit_topic_map(self) -> dict[str, str]:
        """Load mapping from unit_id to topic name."""
        topic_to_unit_path = self._content_dir / "metadata" / "topic_to_unit.json"
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
        if len(parts) != 2:
            return None

        page_num = parts[0]
        for path in [
            self._exercises_dir / page_num / f"{exercise_id}.png",
            self._content_dir / "exercises" / page_num / f"{exercise_id}.png",
        ]:
            if path.exists():
                return path
        return None

    def _load_answers_data(self) -> dict:
        """Load answers data from JSON file."""
        if not self._answers_path.exists():
            return {}
        return json.loads(self._answers_path.read_text(encoding="utf-8"))

    def _load_output(self, output_model: type[BaseModel]) -> BaseModel:
        """Load existing output or return empty model."""
        if self._output_path.exists():
            return output_model.model_validate_json(
                self._output_path.read_text(encoding="utf-8")
            )
        return output_model()

    def _save_output(self, output: BaseModel) -> None:
        """Save output incrementally."""
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")

    def _is_unit_processed(self, output: BaseModel, unit_id: str) -> bool:
        """Check if unit was already processed."""
        return any(u.unit_id == unit_id for u in output.units)

    def _add_unit(self, output: BaseModel, unit: BaseModel) -> None:
        """Add unit to output."""
        output.units.append(unit)

    async def extract(self, output_model: type[BaseModel]) -> dict[str, Path]:
        """Extract data from all units.

        Args:
            output_model: The output model class to use.

        Returns:
            Dict with 'output_path' key containing the output file path.
        """
        data = self._load_answers_data()
        output = self._load_output(output_model)

        for unit in tqdm(data.get("units", []), desc="Processing units"):
            unit_id = unit["unit_id"]
            if self._is_unit_processed(output, unit_id):
                logger.info(f"Skipping already processed unit {unit_id}")
                continue

            unit_data = await self._process_unit(unit)
            self._add_unit(output, unit_data)
            self._save_output(output)

        logger.info(f"Extracted to {self._output_path}")
        return {"output_path": self._output_path}

    async def _process_unit(self, unit: dict) -> BaseModel:
        """Process a unit. Override in subclass."""
        raise NotImplementedError
