"""What the app is holding between taps: the lesson the user is part-way through.

The lesson itself is :mod:`practice_core.lesson`. A run of questions, what a
revealed answer earns, how far along the user is -- none of that is particular
to a phone, and it was written here only because the app grew a lesson mode
first. The bot cannot import this package, so leaving it here meant a second
copy the day the bot wanted one.

What stays is the one thing only this front end remembers: which topic to
offer again on the home screen after a run ends.

Nothing here is persisted. Which lesson is open is a convenience, and a restart
costing the user one run is cheaper than the schema to remember it -- progress,
which is worth keeping, lives in :mod:`practice_app.stats`.
"""

from dataclasses import dataclass

from practice_core.lesson import LESSON_LENGTH, ActiveExercise, Lesson

__all__ = ["LESSON_LENGTH", "ActiveExercise", "Lesson", "PracticeSession"]


@dataclass(slots=True)
class PracticeSession:
    """What the app remembers across lessons."""

    lesson: Lesson | None = None
    # Kept when the lesson ends, so the home screen can offer it again.
    last_topic_id: int | None = None
    last_topic_name: str | None = None

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
