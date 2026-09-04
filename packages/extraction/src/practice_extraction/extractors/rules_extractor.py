"""Extract grammar rules from exercises using LLM."""

import json
from functools import cached_property
from pathlib import Path
from typing import Any

from practice_runtime.logging import get_logger
from practice_runtime.settings import PathSettings

from practice_extraction.agents import RulesAgent
from practice_extraction.models import (
    ExerciseRulesOutput,
    ExtractedExerciseRules,
    ExtractedFullRules,
    ExtractedQuestionRule,
    ExtractedUnitRules,
    RulesQuestion,
)
from practice_extraction.stages import ANSWERS_FULL_FILENAME, RULES_FILENAME

from .unit_store import UnitStore

logger = get_logger(__name__)


class RulesExtractor:
    """Extract grammar rules from exercise images using LLM."""

    def __init__(self, paths: PathSettings, agent: RulesAgent) -> None:
        """Initialize the grammar rule extractor."""
        self._tree = UnitStore(paths, RULES_FILENAME)
        self._extractor_agent = agent
        # Both names come from `stages`, so two stages need not know each other.
        self._answers_full_path = paths.metadata_dir / ANSWERS_FULL_FILENAME

    def _load_answers_full_data(self) -> dict[str, Any]:
        """Load answers_full data from JSON file."""
        if self._answers_full_path.exists():
            return json.loads(self._answers_full_path.read_text(encoding="utf-8"))
        return {}

    def _build_answers_full_map(
        self, answers_full: dict[str, Any]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Index full answer info by ``(exercise_id, question_id)``."""
        return {
            (e["exercise_id"], q["question_id"]): q
            for u in answers_full.get("units", [])
            for e in u.get("exercises", [])
            for q in e.get("questions", [])
        }

    @cached_property
    def _answers_full_map(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Full answers indexed by ``(exercise_id, question_id)``, read once."""
        return self._build_answers_full_map(self._load_answers_full_data())

    async def extract(self) -> Path:
        """Extract grammar rules from all exercises, returning the file written."""
        return await self._tree.extract_units(ExtractedFullRules, self._process_unit)

    async def _process_unit(self, unit: dict) -> ExtractedUnitRules:
        """Process all exercises in a unit."""
        unit_id = unit["unit_id"]
        unit_number = int(unit_id)
        rules_md = self._tree.grammar_markdown(unit_number)
        topic_name = self._tree.topic_name(unit_id)

        if not rules_md:
            logger.warning("grammar_markdown_missing", unit_number=unit_number)
            # RulesContext requires a string; the prompt renders an empty section.
            rules_md = ""

        exercises = [
            await self._process_exercise(ex, rules_md, topic_name)
            for ex in unit.get("exercises", [])
        ]

        return ExtractedUnitRules(unit_id=unit_id, exercises=exercises)

    async def _process_exercise(
        self,
        exercise: dict[str, Any],
        rules_md: str,
        topic_name: str,
    ) -> ExtractedExerciseRules:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._tree.image_path(exercise_id)

        questions_input = self._prepare_questions(exercise)

        result = await self._extractor_agent.extract_exercise(
            image_path=image_path,
            questions=questions_input,
            rules_md=rules_md,
            topic_name=topic_name,
        )
        return self._build_exercise_data(exercise_id, questions_input, result)

    def _prepare_questions(self, exercise: dict[str, Any]) -> list[RulesQuestion]:
        """Prepare questions for extraction."""
        questions = []
        for question in exercise.get("questions", []):
            question_id = question["question_id"]

            key = (exercise["exercise_id"], question_id)
            full_info = self._answers_full_map.get(key, {})
            answers = full_info.get("answers", [])

            questions.append(
                RulesQuestion(
                    question_id=question_id,
                    short_answers=[a["short_answer"] for a in answers],
                    full_answers=[a["full_answer"] for a in answers],
                )
            )
        return questions

    def _build_exercise_data(
        self,
        exercise_id: str,
        questions_input: list[RulesQuestion],
        result: ExerciseRulesOutput,
    ) -> ExtractedExerciseRules:
        """Build exercise data from extraction result."""
        result_map = {q.question_id: q for q in result.questions}

        questions = []
        for q_input in questions_input:
            question_id = q_input.question_id
            q_result = result_map.get(question_id)
            if q_result is None:
                # Skipping costs one rule; raising costs the unit's paid calls.
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
