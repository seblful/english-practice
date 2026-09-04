"""What the app is holding between taps: the lesson the user is part-way through."""

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
        """Start a run and make it the current one."""
        lesson = Lesson(topic_id=topic_id, topic_name=topic_name, length=length)
        self.lesson = lesson
        if topic_id is not None:
            self.last_topic_id = topic_id
            self.last_topic_name = topic_name
        return lesson

    def end(self) -> None:
        """Leave the lesson, keeping the topic for next time."""
        self.lesson = None
