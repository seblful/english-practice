"""Extract full answers from exercises using LLM."""

from pathlib import Path

from practice_runtime.logging import get_logger
from practice_runtime.settings import PathSettings

from practice_extraction.agents import AnswersAgent
from practice_extraction.models import (
    AnswersQuestion,
    ExerciseAnswersOutput,
    ExtractedAnswer,
    ExtractedExerciseAnswers,
    ExtractedFullAnswers,
    ExtractedQuestionAnswers,
    ExtractedUnitAnswers,
)
from practice_extraction.stages import ANSWERS_FULL_FILENAME

from .unit_store import UnitStore

logger = get_logger(__name__)


class AnswersExtractor:
    """Extract full answers from exercise images using LLM."""

    def __init__(self, paths: PathSettings, agent: AnswersAgent) -> None:
        """Initialize the full answer extractor."""
        self._tree = UnitStore(paths, ANSWERS_FULL_FILENAME)
        self._extractor_agent = agent

    async def _process_unit(self, unit: dict) -> ExtractedUnitAnswers:
        """Process all exercises in a unit."""
        unit_id = unit["unit_id"]
        topic_name = self._tree.topic_name(unit_id)

        exercises = [
            await self._process_exercise(ex, topic_name)
            for ex in unit.get("exercises", [])
        ]

        return ExtractedUnitAnswers(unit_id=unit_id, exercises=exercises)

    async def _process_exercise(
        self,
        exercise: dict,
        topic_name: str,
    ) -> ExtractedExerciseAnswers:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._tree.image_path(exercise_id)

        questions_input = [
            AnswersQuestion(question_id=q["question_id"], short_answer=q["answer"])
            for q in exercise.get("questions", [])
        ]

        result = await self._extractor_agent.extract_exercise(
            image_path=image_path,
            questions=questions_input,
            topic_name=topic_name,
        )

        return self._build_exercise_data(exercise_id, questions_input, result)

    def _build_exercise_data(
        self,
        exercise_id: str,
        questions_input: list[AnswersQuestion],
        result: ExerciseAnswersOutput,
    ) -> ExtractedExerciseAnswers:
        """Build exercise data from extraction result."""
        result_map = {q.question_id: q for q in result.questions}

        questions = []
        for q_input in questions_input:
            question_id = q_input.question_id
            q_result = result_map.get(question_id)
            if q_result is None:
                # Skipping costs one question; raising costs the unit's paid calls.
                logger.warning(
                    "question_missing_from_extraction",
                    exercise_id=exercise_id,
                    question_id=question_id,
                )
                continue

            if q_result.is_open_ended:
                questions.append(
                    ExtractedQuestionAnswers(
                        question_id=question_id,
                        is_open_ended=True,
                        answers=[],
                    )
                )
            else:
                # zip would drop an answer the model gave no sentence for.
                full_answers = q_result.full_answers
                answers = [
                    ExtractedAnswer(
                        short_answer=sa,
                        full_answer=(full_answers[i] if i < len(full_answers) else "")
                        or f"[{sa}]",
                    )
                    for i, sa in enumerate(q_result.short_answers)
                ]
                questions.append(
                    ExtractedQuestionAnswers(
                        question_id=question_id,
                        is_open_ended=False,
                        answers=answers,
                    )
                )

        return ExtractedExerciseAnswers(exercise_id=exercise_id, questions=questions)

    async def extract(self) -> Path:
        """Extract full answers from all exercises, returning the file written."""
        return await self._tree.extract_units(ExtractedFullAnswers, self._process_unit)
