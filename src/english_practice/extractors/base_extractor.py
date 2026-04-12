"""Base extractor class with shared functionality."""

from pathlib import Path

from tqdm import tqdm

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


class BaseExtractor:
    """Base class for extractors with shared functionality."""

    def __init__(
        self,
        output_path: Path,
        answers_path: Path | None = None,
    ) -> None:
        """Initialize the base extractor.

        Args:
            output_path: Path to the output JSON file.
            answers_path: Path to answers.json (optional).
        """
        self._output_path = output_path
        self._answers_path = answers_path

    def _get_image_path(self, exercise_id: str) -> Path | None:
        """Get the image path for an exercise."""
        parts = exercise_id.split(".")
        if len(parts) != 2:
            return None

        page_num = parts[0]
        image_path = settings.paths.exercises_dir / page_num / f"{exercise_id}.png"

        if image_path.exists():
            return image_path

        image_path = (
            settings.paths.content_dir / "exercises" / page_num / f"{exercise_id}.png"
        )
        if image_path.exists():
            return image_path

        return None

    def _load_answers_data(self) -> dict:
        """Load answers data from JSON file."""
        if not self._answers_path:
            return {}
        if not self._answers_path.exists():
            raise FileNotFoundError(f"answers.json not found at {self._answers_path}")
        import json

        return json.loads(self._answers_path.read_text(encoding="utf-8"))

    def _load_existing_output(self) -> dict:
        """Load existing output file if it exists."""
        import json

        if self._output_path.exists():
            return json.loads(self._output_path.read_text(encoding="utf-8"))
        return {"units": []}

    def _save_output(self, results: dict) -> None:
        """Save output incrementally."""
        import json

        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _get_processed_unit_ids(self, results: dict) -> set[str]:
        """Get set of already processed unit IDs."""
        return {u["unit_id"] for u in results.get("units", [])}

    async def _process_unit(self, unit: dict) -> dict:
        """Process all exercises in a unit.

        Override in subclass to implement specific exercise processing.
        """
        unit_data = {
            "unit_id": unit["unit_id"],
            "exercises": [],
        }

        for exercise in tqdm(unit.get("exercises", []), desc=f"Unit {unit['unit_id']}"):
            exercise_data = await self._process_exercise(exercise)
            unit_data["exercises"].append(exercise_data)

        return unit_data

    async def _process_exercise(self, exercise: dict) -> dict:
        """Process a single exercise.

        Override in subclass.
        """
        raise NotImplementedError

    async def extract(self) -> dict[str, Path]:
        """Extract data from all units.

        Returns:
            Dict with 'output_path' key containing the output file path.
        """
        results = self._load_existing_output()
        data = self._load_answers_data()
        processed_unit_ids = self._get_processed_unit_ids(results)

        for unit in tqdm(data.get("units", []), desc="Processing units"):
            if unit["unit_id"] in processed_unit_ids:
                logger.info(f"Skipping already processed unit {unit['unit_id']}")
                continue

            unit_data = await self._process_unit(unit)
            results["units"].append(unit_data)
            self._save_output(results)

        logger.info(f"Extracted to {self._output_path}")
        return {"output_path": self._output_path}
