"""Evaluate agent: decides whether the student's answer is correct."""

from collections.abc import Sequence

from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import Question, QuestionAnswer
from practice_core.prompts import render_evaluate_prompt
from practice_runtime.agents import BaseAgent
from practice_runtime.tracing import traced

__all__ = ["EvaluateAnswerAgent"]


class EvaluateAnswerAgent(BaseAgent):
    """Grades a student's answer against the book's expected answers."""

    @traced(name="evaluate_answer")
    async def evaluate(
        self,
        question: Question,
        *,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        topic_name: str,
        image: bytes | None = None,
    ) -> EvaluateAnswerOutput:
        """Grade the student's answer."""
        context = EvaluateAnswerInput.for_question(
            question,
            user_input=user_input,
            answers=answers,
            topic_name=topic_name,
        )

        return await self.invoke_structured(
            prompt=render_evaluate_prompt(context),
            output_model=EvaluateAnswerOutput,
            image=image,
        )
