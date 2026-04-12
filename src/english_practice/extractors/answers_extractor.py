"""Extract full answers from exercises using LLM."""

import json
from pathlib import Path

from tqdm import tqdm

from config.logging import get_logger
from config.settings import settings
from english_practice.agents import AnswersAgent

logger = get_logger(__name__)


class AnswersExtractor:
    """Extract full answers from exercise images using LLM."""

    def __init__(self) -> None:
        """Initialize the full answer extractor."""
        self._extractor = AnswersAgent()
        self._answers_path = settings.paths.metadata_dir / "answers.json"
        self._output_path = settings.paths.metadata_dir / "answers_full.json"

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
        if not self._answers_path.exists():
            raise FileNotFoundError(f"answers.json not found at {self._answers_path}")
        return json.loads(self._answers_path.read_text(encoding="utf-8"))

    def _load_existing_output(self) -> dict:
        """Load existing output file if it exists."""
        if self._output_path.exists():
            return json.loads(self._output_path.read_text(encoding="utf-8"))
        return {"units": []}

    def _save_output(self, results: dict) -> None:
        """Save output incrementally."""
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _get_processed_unit_ids(self, results: dict) -> set[str]:
        """Get set of already processed unit IDs."""
        return {u["unit_id"] for u in results.get("units", [])}

    async def extract(self) -> dict[str, Path]:
        """Extract full answers from all exercises.

        Returns:
            Dict with 'output_path' key containing the output file path
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

        logger.info(f"Full answers extracted to {self._output_path}")
        return {"output_path": self._output_path}

    async def _process_unit(self, unit: dict) -> dict:
        """Process all exercises in a unit."""
        unit_data = {
            "unit_id": unit["unit_id"],
            "exercises": [],
        }

        for exercise in tqdm(unit.get("exercises", []), desc=f"Unit {unit['unit_id']}"):
            exercise_data = await self._process_exercise(exercise)
            unit_data["exercises"].append(exercise_data)

        return unit_data

    async def _process_exercise(self, exercise: dict) -> dict:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._get_image_path(exercise_id)

        if not image_path:
            logger.warning(f"Image not found for {exercise_id}, skipping")
            return self._create_fallback_exercise_data(exercise)

        questions_for_extraction = []
        for question in exercise.get("questions", []):
            question_id = question["question_id"]
            short_answer = question["answer"]
            questions_for_extraction.append(
                {
                    "question_id": question_id,
                    "short_answer": short_answer,
                }
            )

        result = await self._extractor.extract_exercise(
            image_path=image_path,
            questions=questions_for_extraction,
            topic_name="English Grammar",
        )
        return self._build_exercise_data(questions_for_extraction, result)

    def _build_exercise_data(
        self,
        questions_input: list[dict],
        result,
    ) -> dict:
        """Build exercise data from extraction result."""
        exercise_data = {
            "exercise_id": "",
            "questions": [],
        }

        result_map = {q.question_id: q for q in result.questions}

        for q_input in questions_input:
            question_id = q_input["question_id"]
            short_answer = q_input["short_answer"]
            q_result = result_map.get(question_id)

            exercise_data["questions"].append(
                self._build_question_data(question_id, short_answer, q_result)
            )

        if questions_input:
            exercise_data["exercise_id"] = questions_input[0].get("exercise_id", "")

        return exercise_data

    def _build_question_data(
        self,
        question_id: str,
        short_answer: str,
        q_result,
    ) -> dict:
        """Build question data from extraction result."""
        if not q_result:
            return {
                "question_id": question_id,
                "is_open_ended": False,
                "answers": [
                    {
                        "short_answer": short_answer,
                        "full_answer": f"[Missing: {short_answer}]",
                    }
                ],
            }

        if q_result.is_open_ended:
            return {
                "question_id": question_id,
                "is_open_ended": True,
                "answers": [],
            }

        return {
            "question_id": question_id,
            "is_open_ended": False,
            "answers": [
                {
                    "short_answer": short_answer,
                    "full_answer": q_result.full_answer or f"[{short_answer}]",
                }
            ],
        }

    def _create_fallback_exercise_data(self, exercise: dict) -> dict:
        """Create fallback exercise data when image is not found."""
        exercise_data = {
            "exercise_id": exercise["exercise_id"],
            "questions": [],
        }

        for question in exercise.get("questions", []):
            question_id = question["question_id"]
            short_answer = question["answer"]
            exercise_data["questions"].append(
                {
                    "question_id": question_id,
                    "is_open_ended": False,
                    "answers": [
                        {
                            "short_answer": short_answer,
                            "full_answer": f"[No image: {short_answer}]",
                        }
                    ],
                }
            )

        return exercise_data
