"""Extract grammar rules from exercises using LLM."""

import json
from functools import cached_property
from pathlib import Path

from english_practice.agents import RulesAgent
from english_practice.logging import get_logger
from english_practice.models.agents import ExerciseRulesOutput
from english_practice.models.extraction import (
    ExtractedExerciseRules,
    ExtractedFullRules,
    ExtractedQuestionRule,
    ExtractedUnitRules,
)

from .base_extractor import BaseExtractor

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

    @cached_property
    def _answers_full_map(self) -> dict[str, dict]:
        """Full answers indexed by ``"<exercise_id>:<question_id>"``, read once."""
        return self._build_answers_full_map(self._load_answers_full_data())

    async def extract(self) -> dict[str, Path]:
        """Extract grammar rules from all exercises."""
        return await self._extract_units(ExtractedFullRules)

    async def _process_unit(self, unit: dict) -> ExtractedUnitRules:
        """Process all exercises in a unit."""
        unit_id = unit["unit_id"]
        unit_number = int(unit_id)
        rules_md = self._get_grammar_md(unit_number)
        topic_name = self._get_topic_name(unit_id)

        if not rules_md:
            logger.warning("grammar_markdown_missing", unit_number=unit_number)
            # RulesContext requires a string; the prompt renders an empty
            # rules section rather than failing validation.
            rules_md = ""

        exercises = [
            await self._process_exercise(ex, rules_md, topic_name)
            for ex in unit.get("exercises", [])
        ]

        return ExtractedUnitRules(unit_id=unit_id, exercises=exercises)

    async def _process_exercise(
        self,
        exercise: dict,
        rules_md: str,
        topic_name: str,
    ) -> ExtractedExerciseRules:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._get_image_path(exercise_id)

        questions_input = self._prepare_questions(exercise)

        result = await self._extractor_agent.extract_exercise(
            image_path=image_path,
            questions=questions_input,
            rules_md=rules_md,
            topic_name=topic_name,
        )
        return self._build_exercise_data(exercise_id, questions_input, result)

    def _prepare_questions(self, exercise: dict) -> list[dict]:
        """Prepare questions for extraction."""
        questions = []
        for question in exercise.get("questions", []):
            question_id = question["question_id"]

            key = f"{exercise['exercise_id']}:{question_id}"
            full_info = self._answers_full_map.get(key, {})
            is_open_ended = full_info.get("is_open_ended", False)
            answers = full_info.get("answers", [])
            full_answers = [a["full_answer"] for a in answers] if answers else []
            short_answers = [a["short_answer"] for a in answers] if answers else []

            questions.append(
                {
                    "question_id": question_id,
                    "is_open_ended": is_open_ended,
                    "short_answers": short_answers,
                    "full_answers": full_answers,
                }
            )
        return questions

    def _build_exercise_data(
        self,
        exercise_id: str,
        questions_input: list[dict],
        result: ExerciseRulesOutput,
    ) -> ExtractedExerciseRules:
        """Build exercise data from extraction result."""
        result_map = {q.question_id: q for q in result.questions}

        questions = []
        for q_input in questions_input:
            question_id = q_input["question_id"]
            q_result = result_map.get(question_id)
            if q_result is None:
                # Skipping costs one question's rule; raising would discard
                # every already-paid call in the unit.
                logger.warning(
                    "question_missing_from_extraction",
                    exercise_id=exercise_id,
                    question_id=question_id,
                )
                continue

            questions.append(
                ExtractedQuestionRule(
                    question_id=question_id,
                    section_letter=q_result.section_letter,
                    rule=q_result.rule,
                )
            )

        return ExtractedExerciseRules(exercise_id=exercise_id, questions=questions)
