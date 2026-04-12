"""Extract full answers from exercises using LLM."""

from config.logging import get_logger
from config.settings import settings
from english_practice.agents import AnswersAgent

from .base_extractor import BaseExtractor

logger = get_logger(__name__)


class AnswersExtractor(BaseExtractor):
    """Extract full answers from exercise images using LLM."""

    def __init__(self) -> None:
        """Initialize the full answer extractor."""
        super().__init__(
            output_path=settings.paths.metadata_dir / "answers_full.json",
            answers_path=settings.paths.metadata_dir / "answers.json",
        )
        self._extractor = AnswersAgent()

    async def _process_exercise(self, exercise: dict) -> dict:
        """Process a single exercise."""
        exercise_id = exercise["exercise_id"]
        image_path = self._get_image_path(exercise_id)

        questions_for_extraction = [
            {
                "question_id": q["question_id"],
                "short_answer": q["answer"],
            }
            for q in exercise.get("questions", [])
        ]

        result = await self._extractor.extract_exercise(
            image_path=image_path,
            questions=questions_for_extraction,
            topic_name="English Grammar",
        )
        return self._build_exercise_data(exercise_id, questions_for_extraction, result)

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
            short_answer = q_input["short_answer"]
            q_result = result_map.get(question_id)

            if not q_result:
                questions.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": False,
                        "answers": [
                            {
                                "short_answer": short_answer,
                                "full_answer": f"[Missing: {short_answer}]",
                            }
                        ],
                    }
                )
            elif q_result.is_open_ended:
                questions.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": True,
                        "answers": [],
                    }
                )
            else:
                questions.append(
                    {
                        "question_id": question_id,
                        "is_open_ended": False,
                        "answers": [
                            {
                                "short_answer": short_answer,
                                "full_answer": q_result.full_answer
                                or f"[{short_answer}]",
                            }
                        ],
                    }
                )

        return {
            "exercise_id": exercise_id,
            "questions": questions,
        }
