"""Evaluate agent: decides whether the student's answer is correct.

The prompt is not this agent's own. It comes from
:func:`practice_core.prompts.render_evaluate_prompt`, shared with the Android
app, so a change to the grading rules reaches both front ends at once — the one
place where a divergence would show up as different marks for the same answer.
"""

from collections.abc import Sequence

from practice_core.grading import EvaluateAnswerInput, EvaluateAnswerOutput
from practice_core.models import QuestionAnswer
from practice_core.prompts import render_evaluate_prompt
from practice_runtime.agents import BaseAgent
from practice_runtime.tracing import traced

__all__ = ["EvaluateAnswerAgent"]


class EvaluateAnswerAgent(BaseAgent):
    """Grades a student's answer against the book's expected answers."""

    @traced(name="evaluate_answer")
    async def evaluate(
        self,
        *,
        image_data: bytes | None,
        question_number: str,
        user_input: str,
        answers: Sequence[QuestionAnswer],
        is_open_ended: bool,
        topic_name: str,
        rule: str | None = None,
    ) -> EvaluateAnswerOutput:
        """Grade the student's answer.

        Args:
            image_data: Raw exercise image bytes, if the exercise has one.
            question_number: The question number/ID.
            user_input: The student's answer.
            answers: Expected answers in display order; ``answer_idx`` in the
                result indexes into this sequence.
            is_open_ended: Whether the question allows free-form responses.
            topic_name: The topic name, for context.
            rule: The grammar rule for this question, when known.

        Returns:
            Whether the answer is correct, and which expected answers matched.

        Raises:
            AgentError: If the LLM call fails or cannot be parsed.
        """
        context = EvaluateAnswerInput(
            question_number=question_number,
            user_input=user_input,
            answers=list(answers),
            is_open_ended=is_open_ended,
            topic_name=topic_name,
            rule=rule,
        )

        return await self.invoke_structured(
            prompt=render_evaluate_prompt(context),
            output_model=EvaluateAnswerOutput,
            image_data=image_data,
        )
