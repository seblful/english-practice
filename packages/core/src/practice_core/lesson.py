"""Where a student is in a run of questions.

Both front ends draw an exercise, put one question in front of the user and
remember what came back, so "what is on screen and where it came from" is
domain rather than presentation. It used to be declared twice under the same
name, with the same docstring paragraph, once per front end -- and
:class:`Lesson`, which is nothing but data over :mod:`practice_core.models`,
sat inside the app where the bot could not reach it. A lesson mode for the bot
would have meant a third copy.

Every way of settling a question goes through a transition on
:class:`ActiveExercise`. There used to be five overlapping flags for the one
fact -- ``evaluation``, ``ungraded`` and ``is_revealed`` here, ``answered``
and ``grading`` on a subclass in the bot -- with each front end maintaining a
different pair. A grading that failed in the bot showed the book's answer and
set neither of the two this module reads, so ``is_revealed`` said no with the
answer on the user's screen.
"""

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

# What a question drawn from every topic is filed under when the book does not
# say which topic its unit belongs to.
RANDOM_TOPIC_LABEL = "Random"


def topic_label(*, topic_name: str | None, unit: Unit) -> str:
    """Return what to call the topic a drawn question belongs to.

    Args:
        topic_name: The name of the topic the run asked for, or ``None`` for a
            mixed run that took whatever came up.
        unit: The unit the question came from.

    Returns:
        The requested topic, else the one the book files the unit under, else
        :data:`RANDOM_TOPIC_LABEL`.
    """
    return topic_name or unit.topic_name or RANDOM_TOPIC_LABEL


@dataclass(slots=True)
class ActiveExercise:
    """The exercise and question the user is working on right now.

    Grouping them makes the states that used to be spellable -- a question
    without its exercise, an exercise without its unit -- impossible. The
    image and the answers travel with them because neither can change while
    the exercise is on screen, and both are needed on every later step: the
    image is a few hundred kilobytes read once rather than per message.
    """

    exercise: Exercise
    question: Question
    topic_id: int | None
    topic_name: str
    image: bytes | None = None
    answers: tuple[QuestionAnswer, ...] = ()
    evaluation: EvaluateAnswerOutput | None = None
    # Set when the answer was revealed without a verdict -- either the user
    # asked, or grading failed. No verdict is then claimed.
    ungraded: bool = False
    # Held for the length of one grading call. Public so a front end can see
    # a claim it did not make; claimed only through `being_graded`.
    grading: bool = False

    @property
    def answered(self) -> bool:
        """Whether a verdict has come back for this question.

        A grading that failed does not count: the bot offers another attempt,
        and this is the flag that decides whether the next message it gets is
        one. The bot used to carry a field of its own for this, set beside
        ``evaluation`` and meaning the same thing.
        """
        return self.evaluation is not None

    @property
    def is_revealed(self) -> bool:
        """Whether the book's answer has been shown for this question."""
        return self.answered or self.ungraded

    def record(self, evaluation: EvaluateAnswerOutput) -> None:
        """Take the model's verdict for this question.

        Args:
            evaluation: What the model said.
        """
        self.evaluation = evaluation
        self.ungraded = False

    def give_up(self) -> None:
        """Show the book's answer without claiming a verdict.

        Either the student asked for it or the grading failed. Both front ends
        need the distinction: it is what stops a revealed answer counting as a
        right one, and what tells the bot the question is still open.
        """
        self.ungraded = True

    @contextmanager
    def being_graded(self) -> Iterator[None]:
        """Hold this question for the length of one grading call.

        The claim has to be taken before the first ``await``, and released
        however the grading ends. Written out by hand in the bot's handler,
        it was taken late -- ``evaluation`` only arrives once the verdict is
        back -- so two messages sent at once were both graded: one answer, two
        provider calls, two contradictory verdicts.

        Yields:
            Nothing; the claim is the point.
        """
        self.grading = True
        try:
            yield
        finally:
            self.grading = False

    def reveal(self, *, show_rule: bool = True) -> Reveal:
        """Return what to show the student for this question.

        Args:
            show_rule: Whether the student has rules turned on.

        Returns:
            The answers to print and the decisions around them.
        """
        return reveal_for(
            self.question,
            answers=self.answers,
            unit_number=self.exercise.unit.unit_number,
            evaluation=self.evaluation,
            show_rule=show_rule,
        )


@dataclass(slots=True)
class Lesson:
    """One run of a fixed number of questions.

    The outcomes are the single record of how the run is going: a progress
    bar, the counter beside it and the result at the end are all read off this
    list, so none of them can disagree with another.

    The transitions are the reason this is a module and not a bag of fields.
    Recording an outcome used to be the caller's duty, which meant the rule
    this class documents -- a revealed answer counts as done but never as
    correct -- was enforced by whoever remembered to pass ``correct=False``.
    Every way an outcome can be added now goes through one of them.
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
        """Which question is on screen, counting from one.

        An answer is recorded the moment it is given, while its verdict stays
        on screen until the user moves on. Counting straight off ``answered``
        therefore announced the next question while the previous one's answer
        was still being read -- "2/10" over the verdict for question one.
        """
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
        """Put the next question on screen.

        Args:
            active: The exercise and question just drawn.
        """
        self.active = active

    def finish(self) -> None:
        """Take the last question off screen, the run being over.

        Pairs with :meth:`advance`, so that whether a question is on screen is
        this class's to say and not a field a caller reaches in and clears.
        """
        self.active = None

    def check(self, evaluation: EvaluateAnswerOutput) -> ActiveExercise:
        """Record the model's verdict for the question on screen.

        Args:
            evaluation: What the model said.

        Returns:
            The question the verdict belongs to.

        Raises:
            PracticeError: If no question is on screen, or that question has
                already been settled.
        """
        active = self._unsettled()
        active.record(evaluation)
        self.outcomes.append(evaluation.is_correct)
        return active

    def reveal_answer(self) -> ActiveExercise:
        """Give up on the question on screen and show the book's answer.

        Returns:
            The question that was revealed.

        Raises:
            PracticeError: If no question is on screen.
        """
        return self._spend()

    def grading_failed(self) -> ActiveExercise:
        """Note that the question on screen could not be graded.

        A run has a fixed length, so the question is spent either way: there is
        nowhere to put a retry without the bar and the counter disagreeing
        about how far along the user is. The bot, whose stream has no length,
        offers another attempt instead -- which is why the policy is applied
        here and not in :mod:`practice_core.reveal`.

        Returns:
            The question that could not be graded.

        Raises:
            PracticeError: If no question is on screen.
        """
        return self._spend()

    def _spend(self) -> ActiveExercise:
        """Mark the question on screen as revealed without a verdict.

        Returns:
            The question that was spent.

        Raises:
            PracticeError: If no question is on screen, or that question has
                already been settled.
        """
        active = self._unsettled()
        active.give_up()
        self.outcomes.append(False)
        return active

    def _unsettled(self) -> ActiveExercise:
        """Return the question on screen, which must not have an outcome yet.

        The run has a fixed number of slots and every transition takes one, so
        settling the same question twice spends two of them: the bar and the
        counter then report a lesson longer than the one the student sat.
        Nothing here enforced it -- the app was safe only because the screen
        hides the Check button once an answer is revealed.

        Returns:
            The active exercise, still open.

        Raises:
            PracticeError: If no question is on screen, or the one on screen
                has already been settled.
        """
        active = self._on_screen()
        if active.is_revealed:
            raise PracticeError("this question already has an outcome")
        return active

    def _on_screen(self) -> ActiveExercise:
        """Return the question in front of the user.

        Returns:
            The active exercise.

        Raises:
            PracticeError: If no question is on screen, which means a caller
                acted on a verdict for a lesson that has not drawn one.
        """
        if self.active is None:
            raise PracticeError("no question is on screen")
        return self.active
