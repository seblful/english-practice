"""Extract grammar rules from exercises using LLM."""

import json
from pathlib import Path

from tqdm import tqdm

from config.logging import get_logger
from config.settings import settings
from english_practice.agents import RulesAgent

logger = get_logger(__name__)


class RulesExtractor:
    """Extract grammar rules from exercise images using LLM."""

    def __init__(self) -> None:
        """Initialize the grammar rule extractor."""
        self._extractor = RulesAgent()
        self._answers_path = settings.paths.metadata_dir / "answers.json"
        self._answers_full_path = settings.paths.metadata_dir / "answers_full.json"
        self._output_path = settings.paths.metadata_dir / "rules.json"

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

    def _get_grammar_md(self, unit_number: int) -> str | None:
        """Get grammar markdown content for a unit."""
        grammar_path = settings.paths.grammar_md_dir / f"{unit_number}.md"
        if grammar_path.exists():
            return grammar_path.read_text(encoding="utf-8")

        grammar_path = settings.paths.content_dir / "grammar" / f"{unit_number}.md"
        if grammar_path.exists():
            return grammar_path.read_text(encoding="utf-8")

        return None

    def _load_answers_data(self) -> dict:
        """Load answers data from JSON file."""
        if not self._answers_path.exists():
            raise FileNotFoundError(f"answers.json not found at {self._answers_path}")
        return json.loads(self._answers_path.read_text(encoding="utf-8"))

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
        """Extract grammar rules from all exercises.

        Returns:
            Dict with 'output_path' key containing the output file path
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
            return self._create_skipped_exercise_data(questions_for_extraction)

        result = await self._extractor.extract_exercise(
            image_path=image_path,
            questions=questions_for_extraction,
            rules_md=rules_md or "",
            topic_name="English Grammar",
        )
        return self._build_exercise_data(questions_for_extraction, result)

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

    def _create_skipped_exercise_data(self, questions: list[dict]) -> dict:
        """Create exercise data when extraction is skipped."""
        exercise_data = {
            "exercise_id": "",
            "questions": [],
        }

        for q in questions:
            exercise_data["questions"].append(
                {
                    "question_id": q["question_id"],
                    "is_open_ended": q["is_open_ended"],
                    "section_letter": None,
                    "rule": None,
                }
            )

        return exercise_data

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
            q_result = result_map.get(question_id)

            exercise_data["questions"].append(
                self._build_question_data(q_input, q_result)
            )

        if questions_input:
            exercise_data["exercise_id"] = questions_input[0].get("exercise_id", "")

        return exercise_data

    def _build_question_data(self, q_input: dict, q_result) -> dict:
        """Build question data from extraction result."""
        if q_input["is_open_ended"]:
            return {
                "question_id": q_input["question_id"],
                "is_open_ended": True,
                "section_letter": None,
                "rule": None,
            }

        if q_result:
            return {
                "question_id": q_input["question_id"],
                "is_open_ended": False,
                "section_letter": q_result.section_letter,
                "rule": q_result.rule,
            }

        return {
            "question_id": q_input["question_id"],
            "is_open_ended": False,
            "section_letter": None,
            "rule": "[Missing]",
        }
