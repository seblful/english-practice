"""What the app is holding between taps: the exercise in front of the user.

Nothing here is persisted. Which exercise is open is a convenience, and a
restart costing the user one tap is cheaper than the schema to remember it —
progress, which is worth keeping, lives in :mod:`practice.stats`.
"""

from dataclasses import dataclass

from practice_core.grading import EvaluateAnswerOutput, answers_to_show
from practice_core.models import Exercise, Question, QuestionAnswer

__all__ = ["ActiveExercise", "PracticeSession"]


@dataclass(slots=True)
class ActiveExercise:
    """The exercise and question the user is working on right now.

    Grouping them makes the states that used to be spellable — a question
    without its exercise, an exercise without its unit — impossible. The image
    and the answers travel with them because neither can change while the
    exercise is on screen, and both are needed on every later tap.
    """

    exercise: Exercise
    question: Question
    topic_id: int | None
    topic_name: str
    image: bytes | None = None
    answers: tuple[QuestionAnswer, ...] = ()
    evaluation: EvaluateAnswerOutput | None = None
    # Set when the answer was revealed without a verdict — either the user
    # asked, or grading failed. The attempt is then not counted in the stats
    # and no verdict is claimed.
    ungraded: bool = False

    @property
    def is_revealed(self) -> bool:
        """Whether the book's answer has been shown for this question."""
        return self.evaluation is not None or self.ungraded

    @property
    def revealed_answers(self) -> tuple[QuestionAnswer, ...]:
        """Return the answers to show, once the question has been answered."""
        if self.evaluation is None:
            return tuple(self.answers[:1]) if self.ungraded else ()
        return answers_to_show(self.answers, self.evaluation.answer_idx)

    @property
    def unit_reference(self) -> str:
        """Return the unit and section this question came from."""
        return f"{self.exercise.unit.unit_number}{self.question.section_letter or ''}"


@dataclass(slots=True)
class PracticeSession:
    """What the app remembers across exercises."""

    active: ActiveExercise | None = None
    # Kept when the exercise is cleared, so "Again" survives a new draw.
    last_topic_id: int | None = None
    last_topic_name: str | None = None

    @property
    def has_previous_topic(self) -> bool:
        """Whether the user has already practised a specific topic."""
        return self.last_topic_id is not None

    def start(self, active: ActiveExercise) -> None:
        """Make an exercise the current one.

        Args:
            active: The exercise and question just drawn.
        """
        self.active = active
        if active.topic_id is not None:
            self.last_topic_id = active.topic_id
            self.last_topic_name = active.topic_name

    def clear(self) -> None:
        """Forget the current exercise, keeping the last topic."""
        self.active = None
