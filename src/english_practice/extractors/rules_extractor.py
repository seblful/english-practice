"""Extract grammar rules from exercises using LLM."""

import json
from pathlib import Path

from tqdm import tqdm

from config.logging import get_logger
from config.settings import settings
from english_practice.agents import RulesAgent

from .base_extractor import BaseExtractor

logger = get_logger(__name__)


class RulesExtractor(BaseExtractor):
    """Extract grammar rules from exercise images using LLM."""

    def __init__(self) -> None:
        """Initialize the grammar rule extractor."""
        super().__init__(
            output_path=settings.paths.metadata_dir / "rules.json",
            answers_path=settings.paths.metadata_dir / "answers.json",
        )
        self._extractor = RulesAgent()
        self._answers_full_path = settings.paths.metadata_dir / "answers_full.json"

    def _get_grammar_md(self, unit_number: int) -> str | None:
        """Get grammar markdown content for a unit."""
        grammar_path = settings.paths.grammar_md_dir / f"{unit_number}.md"
        if grammar_path.exists():
            return grammar_path.read_text(encoding="utf-8")

        grammar_path = settings.paths.content_dir / "grammar" / f"{unit_number}.md"
        if grammar_path.exists():
            return grammar_path.read_text(encoding="utf-8")

        return None

    def _load_answers_full_data(self) -> dict:
        """Load answers_full data from JSON file."""
        if self._answers_full_path.exists():
            return json.loads(self._answers_full_path.read_text(encoding="utf-8"))
        return {}

    def _build_answers_full_map(self, answers_full: dict) -> dict:
        """Build a map of exercise:question_id to full answer info."""
        answers_map = {}
        for u in answers_full.get("units", []):
            for e in u.get("exercises", []):
                for q in e.get("questions", []):
                    key = f"{e['exercise_id']}:{q['question_id']}"
                    answers_map[key] = q
        return answers_map

    async def extract(self) -> dict[str, Path]:
        """Extract grammar rules from all exercises.

        Returns:
            Dict with 'output_path' key containing the output file path.
        """
        results = self._load_existing_output()
        data = self._load_answers_data()
        answers_full = self._load_answers_full_data()
        answers_full_map = self._build_answers_full_map(answers_full)
        processed_unit_ids = self._get_processed_unit_ids(results)

        for unit in tqdm(data.get("units", []), desc="Processing units"):
            if unit["unit_id"] in processed_unit_ids:
                logger.info(f"Skipping already processed unit {unit['unit_id']}")
                continue

            unit_data = await self._process_unit(unit, answers_full_map)
            results["units"].append(unit_data)
            self._save_output(results)

        logger.info(f"Rules extracted to {self._output_path}")
        return {"output_path": self._output_path}

    async def _process_unit(self, unit: dict, answers_full_map: dict) -> dict:
        """Process all exercises in a unit."""
        unit_number = int(unit["unit_id"])
        rules_md = self._get_grammar_md(unit_number)

        if not rules_md:
            logger.warning(f"Grammar markdown not found for unit {unit_number}")

        unit_data = {
            "unit_id": unit["unit_id"],
            "exercises": [],
        }

        for exercise in tqdm(unit.get("exercises", []), desc=f"Unit {unit['unit_id']}"):
            exercise_data = await self._process_exercise(
                exercise, answers_full_map, rules_md
            )
            unit_data["exercises"].append(exercise_data)

        return unit_data

    async def _process_exercise(
        self,
        exercise: dict,
        answers_full_map: dict,
        rules_md: str | None,
    ) -> dict:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._get_image_path(exercise_id)

        questions_for_extraction = self._prepare_questions(exercise, answers_full_map)

        if self._should_skip_extraction(questions_for_extraction, image_path, rules_md):
            return self._create_skipped_exercise_data(
                exercise_id, questions_for_extraction
            )

        result = await self._extractor.extract_exercise(
            image_path=image_path,
            questions=questions_for_extraction,
            rules_md=rules_md or "",
            topic_name="English Grammar",
        )
        return self._build_exercise_data(exercise_id, questions_for_extraction, result)

    def _prepare_questions(self, exercise: dict, answers_full_map: dict) -> list[dict]:
        """Prepare questions for extraction."""
        questions = []
        for question in exercise.get("questions", []):
            question_id = question["question_id"]
            short_answer = question["answer"]

            key = f"{exercise['exercise_id']}:{question_id}"
            full_info = answers_full_map.get(key, {})
            is_open_ended = full_info.get("is_open_ended", False)
            answers = full_info.get("answers", [])
            full_answer_str = answers[0]["full_answer"] if answers else ""

            questions.append(
                {
                    "question_id": question_id,
                    "is_open_ended": is_open_ended,
                    "short_answer": short_answer,
                    "full_answer": full_answer_str,
                }
            )
        return questions

    def _should_skip_extraction(
        self,
        questions: list[dict],
        image_path: Path | None,
        rules_md: str | None,
    ) -> bool:
        """Check if extraction should be skipped."""
        if not image_path or not rules_md:
            return True
        if any(q["is_open_ended"] for q in questions):
            return True
        return False

    def _create_skipped_exercise_data(
        self,
        exercise_id: str,
        questions: list[dict],
    ) -> dict:
        """Create exercise data when extraction is skipped."""
        return {
            "exercise_id": exercise_id,
            "questions": [
                {
                    "question_id": q["question_id"],
                    "is_open_ended": q["is_open_ended"],
                    "section_letter": None,
                    "rule": None,
                }
                for q in questions
            ],
        }

    def _build_exercise_data(
        self,
        exercise_id: str,
        questions_input: list[dict],
        result,
    ) -> dict:
        """Build exercise data from extraction result."""
        result_map = {q.question_id: q for q in result.questions}

        questions = []
        for q_input in questions_input:
            question_id = q_input["question_id"]
            q_result = result_map.get(question_id)

            if q_input["is_open_ended"]:
                questions.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": True,
                        "section_letter": None,
                        "rule": None,
                    }
                )
            elif q_result:
                questions.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": False,
                        "section_letter": q_result.section_letter,
                        "rule": q_result.rule,
                    }
                )
            else:
                questions.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": False,
                        "section_letter": None,
                        "rule": "[Missing]",
                    }
                )

        return {
            "exercise_id": exercise_id,
            "questions": questions,
        }
