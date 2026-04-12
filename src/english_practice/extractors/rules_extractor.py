"""Extract grammar rules from exercises using LLM."""

import json
from pathlib import Path

from english_practice.agents import RulesAgent
from english_practice.models.extraction import (
    ExtractedExerciseRules,
    ExtractedFullRules,
    ExtractedQuestionRule,
    ExtractedUnitRules,
)
from tqdm import tqdm

from .base_extractor import BaseExtractor

from config.logging import get_logger


logger = get_logger(__name__)


class RulesExtractor(BaseExtractor):
    """Extract grammar rules from exercise images using LLM."""

    def __init__(
        self,
        output_path: Path,
        answers_path: Path,
        exercises_dir: Path,
        content_dir: Path,
        answers_full_path: Path,
        grammar_md_dir: Path,
    ) -> None:
        """Initialize the grammar rule extractor."""
        super().__init__(
            output_path=output_path,
            answers_path=answers_path,
            exercises_dir=exercises_dir,
            content_dir=content_dir,
        )
        self._extractor_agent = RulesAgent()
        self._answers_full_path = answers_full_path
        self._grammar_md_dir = grammar_md_dir

    def _get_grammar_md(self, unit_number: int) -> str | None:
        """Get grammar markdown content for a unit."""
        for path in [
            self._grammar_md_dir / f"{unit_number}.md",
            self._content_dir / "grammar" / f"{unit_number}.md",
        ]:
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def _load_answers_full_data(self) -> dict:
        """Load answers_full data from JSON file."""
        if self._answers_full_path.exists():
            return json.loads(self._answers_full_path.read_text(encoding="utf-8"))
        return {}

    def _build_answers_full_map(self, answers_full: dict) -> dict[str, dict]:
        """Build a map of exercise:question_id to full answer info."""
        return {
            f"{e['exercise_id']}:{q['question_id']}": q
            for u in answers_full.get("units", [])
            for e in u.get("exercises", [])
            for q in e.get("questions", [])
        }

    async def extract(self) -> dict[str, Path]:
        """Extract grammar rules from all exercises."""
        data = self._load_answers_data()
        answers_full_map = self._build_answers_full_map(self._load_answers_full_data())
        output = self._load_output(ExtractedFullRules)

        for unit in tqdm(data.get("units", []), desc="Processing units"):
            unit_id = unit["unit_id"]
            if self._is_unit_processed(output, unit_id):
                logger.info(f"Skipping already processed unit {unit_id}")
                continue

            unit_data = await self._process_unit(unit, answers_full_map)
            self._add_unit(output, unit_data)
            self._save_output(output)

        logger.info(f"Rules extracted to {self._output_path}")
        return {"output_path": self._output_path}

    async def _process_unit(
        self,
        unit: dict,
        answers_full_map: dict[str, dict],
    ) -> ExtractedUnitRules:
        """Process all exercises in a unit."""
        unit_id = unit["unit_id"]
        unit_number = int(unit_id)
        rules_md = self._get_grammar_md(unit_number)
        topic_name = self._get_topic_name(unit_id)

        if not rules_md:
            logger.warning(f"Grammar markdown not found for unit {unit_number}")

        exercises = [
            await self._process_exercise(ex, answers_full_map, rules_md, topic_name)
            for ex in unit.get("exercises", [])
        ]

        return ExtractedUnitRules(unit_id=unit_id, exercises=exercises)

    async def _process_exercise(
        self,
        exercise: dict,
        answers_full_map: dict[str, dict],
        rules_md: str | None,
        topic_name: str,
    ) -> ExtractedExerciseRules:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._get_image_path(exercise_id)

        questions_input = self._prepare_questions(exercise, answers_full_map)

        if self._should_skip_extraction(questions_input, image_path, rules_md):
            return self._create_skipped_exercise_data(exercise_id, questions_input)

        result = await self._extractor_agent.extract_exercise(
            image_path=image_path,
            questions=questions_input,
            rules_md=rules_md or "",
            topic_name=topic_name,
        )
        return self._build_exercise_data(exercise_id, questions_input, result)

    def _prepare_questions(
        self,
        exercise: dict,
        answers_full_map: dict[str, dict],
    ) -> list[dict]:
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
        return (
            not image_path or not rules_md or any(q["is_open_ended"] for q in questions)
        )

    def _create_skipped_exercise_data(
        self,
        exercise_id: str,
        questions: list[dict],
    ) -> ExtractedExerciseRules:
        """Create exercise data when extraction is skipped."""
        return ExtractedExerciseRules(
            exercise_id=exercise_id,
            questions=[
                ExtractedQuestionRule(
                    question_id=q["question_id"],
                    is_open_ended=q["is_open_ended"],
                    section_letter=None,
                    rule=None,
                )
                for q in questions
            ],
        )

    def _build_exercise_data(
        self,
        exercise_id: str,
        questions_input: list[dict],
        result,
    ) -> ExtractedExerciseRules:
        """Build exercise data from extraction result."""
        result_map = {q.question_id: q for q in result.questions}

        questions = []
        for q_input in questions_input:
            question_id = q_input["question_id"]
            q_result = result_map.get(question_id)

            if q_input["is_open_ended"]:
                questions.append(
                    ExtractedQuestionRule(
                        question_id=question_id,
                        is_open_ended=True,
                        section_letter=None,
                        rule=None,
                    )
                )
            elif q_result:
                questions.append(
                    ExtractedQuestionRule(
                        question_id=question_id,
                        is_open_ended=False,
                        section_letter=q_result.section_letter,
                        rule=q_result.rule,
                    )
                )
            else:
                questions.append(
                    ExtractedQuestionRule(
                        question_id=question_id,
                        is_open_ended=False,
                        section_letter=None,
                        rule="[Missing]",
                    )
                )

        return ExtractedExerciseRules(exercise_id=exercise_id, questions=questions)
