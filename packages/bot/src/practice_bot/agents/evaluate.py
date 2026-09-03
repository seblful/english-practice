"""Evaluate agent: decides whether the student's answer is correct.

Neither the prompt nor the context it renders from is this agent's own. Both
come from :mod:`practice_core`, shared with the Android app, so a change to the
grading rules reaches both front ends at once -- the one place where a
divergence would show up as different marks for the same answer.

What is left here is the call, which is why this class holds one method and no
prompt of its own.
"""

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
        """Grade the student's answer.

        Args:
            question: The question being answered. Its number, its rule and
                whether it is open-ended all come off it, rather than being
                taken apart by the caller and passed back in one at a time.
            user_input: The student's answer.
            answers: Expected answers in display order; ``answer_idx`` in the
                result indexes into this sequence.
            topic_name: The topic name, for context.
            image: Raw exercise image bytes, if the exercise has one.

        Returns:
            Whether the answer is correct, and which expected answers matched.

        Raises:
            AgentError: If the LLM call fails or cannot be parsed.
        """
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
