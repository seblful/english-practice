"""What the app is holding between taps: the lesson the user is part-way through.

A lesson is a fixed run of questions rather than an endless stream. That is
what lets the screen say how far along the user is and show a result when they
are done — "one more question, forever" is the shape that makes an app easy to
put down and never pick up again.

Nothing here is persisted. Which lesson is open is a convenience, and a restart
costing the user one run is cheaper than the schema to remember it — progress,
which is worth keeping, lives in :mod:`practice_app.stats`.
"""

from dataclasses import dataclass, field

from practice_core.grading import EvaluateAnswerOutput, answers_to_show
from practice_core.models import Exercise, Question, QuestionAnswer

__all__ = ["LESSON_LENGTH", "ActiveExercise", "Lesson", "PracticeSession"]

# Long enough to be worth starting, short enough to finish on a bus.
LESSON_LENGTH = 10


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
class Lesson:
    """One run of a fixed number of questions.

    The outcomes are the single record of how the run is going: the bar at the
    top, the counter beside it and the result at the end are all read off this
    list, so none of them can disagree with another.
    """

    topic_id: int | None
    topic_name: str
    length: int = LESSON_LENGTH
    active: ActiveExercise | None = None
    # One entry per question already answered, in the order they were answered.
    # A revealed answer counts as done but never as correct, which is what
    # stops "reveal ten times" from reading as a perfect run.
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

    def record(self, *, correct: bool) -> None:
        """Count the question on screen as answered.

        Args:
            correct: Whether the model marked it right. A revealed answer
                passes ``False``: it is done, but it was not earned.
        """
        self.outcomes.append(correct)


@dataclass(slots=True)
class PracticeSession:
    """What the app remembers across lessons."""

    lesson: Lesson | None = None
    # Kept when the lesson ends, so the home screen can offer it again.
    last_topic_id: int | None = None
    last_topic_name: str | None = None

    @property
    def active(self) -> ActiveExercise | None:
        """Return the question in front of the user, if there is one."""
        return self.lesson.active if self.lesson is not None else None

    @property
    def has_previous_topic(self) -> bool:
        """Whether the user has already practised a specific topic."""
        return self.last_topic_id is not None

    def begin(
        self,
        topic_id: int | None,
        topic_name: str,
        *,
        length: int = LESSON_LENGTH,
    ) -> Lesson:
        """Start a run and make it the current one.

        Args:
            topic_id: The topic to draw from, or ``None`` for a mixed run.
            topic_name: What to call the run on screen.
            length: How many questions it holds.

        Returns:
            The new lesson.
        """
        lesson = Lesson(topic_id=topic_id, topic_name=topic_name, length=length)
        self.lesson = lesson
        if topic_id is not None:
            self.last_topic_id = topic_id
            self.last_topic_name = topic_name
        return lesson

    def end(self) -> None:
        """Leave the lesson, keeping the topic for next time."""
        self.lesson = None
