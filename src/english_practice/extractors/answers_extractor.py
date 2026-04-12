"""Extract full answers from exercises using LLM."""

from pathlib import Path

from english_practice.agents import AnswersAgent
from english_practice.models.extraction import (
    ExtractedAnswer,
    ExtractedExerciseAnswers,
    ExtractedFullAnswers,
    ExtractedQuestionAnswers,
    ExtractedUnitAnswers,
)

from .base_extractor import BaseExtractor


class AnswersExtractor(BaseExtractor):
    """Extract full answers from exercise images using LLM."""

    def __init__(
        self,
        output_path: Path,
        answers_path: Path,
        exercises_dir: Path,
        content_dir: Path,
    ) -> None:
        """Initialize the full answer extractor."""
        super().__init__(
            output_path=output_path,
            answers_path=answers_path,
            exercises_dir=exercises_dir,
            content_dir=content_dir,
        )
        self._extractor_agent = AnswersAgent()

    async def _process_unit(self, unit: dict) -> ExtractedUnitAnswers:
        """Process all exercises in a unit."""
        unit_id = unit["unit_id"]
        topic_name = self._get_topic_name(unit_id)

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
        image_path = self._get_image_path(exercise_id)

        questions_input = [
            {"question_id": q["question_id"], "short_answer": q["answer"]}
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
        questions_input: list[dict],
        result,
    ) -> ExtractedExerciseAnswers:
        """Build exercise data from extraction result."""
        result_map = {q.question_id: q for q in result.questions}

        questions = []
        for q_input in questions_input:
            question_id = q_input["question_id"]
            short_answer = q_input["short_answer"]
            q_result = result_map.get(question_id)

            if not q_result:
                questions.append(
                    ExtractedQuestionAnswers(
                        question_id=question_id,
                        is_open_ended=False,
                        answers=[
                            ExtractedAnswer(
                                short_answer=short_answer,
                                full_answer=f"[Missing: {short_answer}]",
                            )
                        ],
                    )
                )
            elif q_result.is_open_ended:
                questions.append(
                    ExtractedQuestionAnswers(
                        question_id=question_id,
                        is_open_ended=True,
                        answers=[],
                    )
                )
            else:
                answers = []
                for sa, fa in zip(q_result.short_answers, q_result.full_answers):
                    answers.append(
                        ExtractedAnswer(
                            short_answer=sa,
                            full_answer=fa or f"[{sa}]",
                        )
                    )
                questions.append(
                    ExtractedQuestionAnswers(
                        question_id=question_id,
                        is_open_ended=False,
                        answers=answers,
                    )
                )

        return ExtractedExerciseAnswers(exercise_id=exercise_id, questions=questions)

    async def extract(self) -> dict[str, Path]:
        """Extract full answers from all exercises."""
        return await super().extract(ExtractedFullAnswers)
