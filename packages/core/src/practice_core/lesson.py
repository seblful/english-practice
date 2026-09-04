"""Where a student is in a run of questions."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from practice_core.errors import PracticeError
from practice_core.grading import EvaluateAnswerOutput
from practice_core.models import Exercise, Question, QuestionAnswer, Unit
from practice_core.reveal import Reveal, reveal_for

__all__ = [
    "LESSON_LENGTH",
    "RANDOM_TOPIC_LABEL",
    "ActiveExercise",
    "Lesson",
    "topic_label",
]

# Long enough to be worth starting, short enough to finish on a bus.
LESSON_LENGTH = 10

# Where a question is filed when the book does not say which topic it is.
RANDOM_TOPIC_LABEL = "Random"


def topic_label(*, topic_name: str | None, unit: Unit) -> str:
    """Return what to call the topic a drawn question belongs to."""
    return topic_name or unit.topic_name or RANDOM_TOPIC_LABEL


@dataclass(slots=True)
class ActiveExercise:
    """The exercise and question the user is working on right now."""

    exercise: Exercise
    question: Question
    topic_id: int | None
    topic_name: str
    image: bytes | None = None
    answers: tuple[QuestionAnswer, ...] = ()
    evaluation: EvaluateAnswerOutput | None = None
    # Set when the answer was revealed without a verdict, so none is claimed.
    ungraded: bool = False
    # Public so a front end can see a claim it did not make; set by `being_graded`.
    grading: bool = False

    @property
    def answered(self) -> bool:
        """Whether a verdict has come back for this question."""
        return self.evaluation is not None

    @property
    def is_revealed(self) -> bool:
        """Whether the book's answer has been shown for this question."""
        return self.answered or self.ungraded

    def record(self, evaluation: EvaluateAnswerOutput) -> None:
        """Take the model's verdict for this question."""
        self.evaluation = evaluation
        self.ungraded = False

    def give_up(self) -> None:
        """Show the book's answer without claiming a verdict."""
        self.ungraded = True

    @contextmanager
    def being_graded(self) -> Iterator[None]:
        """Hold this question for the length of one grading call."""
        self.grading = True
        try:
            yield
        finally:
            self.grading = False

    def reveal(self, *, show_rule: bool = True) -> Reveal:
        """Return what to show the student for this question."""
        return reveal_for(
            self.question,
            answers=self.answers,
            unit_number=self.exercise.unit.unit_number,
            evaluation=self.evaluation,
            show_rule=show_rule,
        )


@dataclass(slots=True)
class Lesson:
    """One run of a fixed number of questions."""

    topic_id: int | None
    topic_name: str
    length: int = LESSON_LENGTH
    active: ActiveExercise | None = None
    # A revealed answer counts as done but never as correct.
    outcomes: list[bool] = field(default_factory=list)

    @property
    def answered(self) -> int:
        """How many questions of the run are behind the user."""
        return len(self.outcomes)

    @property
    def correct(self) -> int:
        """How many of those were right."""
        return sum(self.outcomes)

    @property
    def position(self) -> int:
        """Which question is on screen, counting from one."""
        if self.active is not None and self.active.is_revealed:
            return self.answered
        return min(self.answered + 1, self.length)

    @property
    def progress(self) -> float:
        """How much of the run is done, from 0 to 1."""
        return min(self.answered / self.length, 1.0)

    @property
    def accuracy(self) -> float:
        """The share of the run answered correctly, from 0 to 1."""
        return self.correct / self.answered if self.answered else 0.0

    @property
    def is_complete(self) -> bool:
        """Whether every question of the run has been answered."""
        return self.answered >= self.length

    def advance(self, active: ActiveExercise) -> None:
        """Put the next question on screen."""
        self.active = active

    def finish(self) -> None:
        """Take the last question off screen, the run being over."""
        self.active = None

    def check(self, evaluation: EvaluateAnswerOutput) -> ActiveExercise:
        """Record the model's verdict for the question on screen."""
        active = self._unsettled()
        active.record(evaluation)
        self.outcomes.append(evaluation.is_correct)
        return active

    def reveal_answer(self) -> ActiveExercise:
        """Give up on the question on screen and show the book's answer."""
        return self._spend()

    def grading_failed(self) -> ActiveExercise:
        """Note that the question on screen could not be graded."""
        return self._spend()

    def _spend(self) -> ActiveExercise:
        """Mark the question on screen as revealed without a verdict."""
        active = self._unsettled()
        active.give_up()
        self.outcomes.append(False)
        return active

    def _unsettled(self) -> ActiveExercise:
        """Return the question on screen, which must not have an outcome yet."""
        active = self._on_screen()
        if active.is_revealed:
            raise PracticeError("this question already has an outcome")
        return active

    def _on_screen(self) -> ActiveExercise:
        """Return the question in front of the user."""
        if self.active is None:
            raise PracticeError("no question is on screen")
        return self.active
