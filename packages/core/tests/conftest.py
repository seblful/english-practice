"""Shared fixtures for the core tests.

The database is built from the schema this package ships rather than a
hand-written copy: a column renamed there should break these tests instead of
production.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from practice_core.content import ContentLibrary
from practice_core.models import Exercise, Question, QuestionAnswer, Topic, Unit
from practice_core.schema import create_content_schema

SEED = """
INSERT INTO units (id, unit_number, title)
VALUES (1, 1, 'Present Continuous'), (2, 2, 'Past Simple');

INSERT INTO topics (id, name) VALUES (1, 'Present Tenses'),
                                     (2, 'Past Tenses'),
                                     (3, 'Unused Topic');

INSERT INTO unit_topics (unit_id, topic_id) VALUES (1, 1), (2, 2);

INSERT INTO exercises (id, exercise_id, unit_id, exercise_number)
VALUES (1, '1.1', 1, 1), (2, '1.2', 1, 2), (3, '2.1', 2, 1);

INSERT INTO exercise_images (exercise_id, image_data)
VALUES (1, X'89504E47'), (3, X'');

INSERT INTO questions
    (id, exercise_id, question_id, is_open_ended,
     section_letter, rule, display_order)
VALUES
    (1, 1, '2', 0, 'A', 'Use present continuous', 1),
    (2, 1, '1', 1, 'B', NULL, 0),
    (3, 3, '1', 0, 'A', 'Use past simple', 0);

INSERT INTO question_answers (question_id, short_answer, full_answer)
VALUES (1, 'is doing', 'He is doing.'),
       (1, "'s doing", "He's doing.");
"""


@pytest.fixture
def seeded_db_path(tmp_path: Path) -> Path:
    """Build a database from the project schema, with a little content.

    Exercise 2 deliberately has no questions, topic 3 no units, and exercise 3
    a zero-length image blob, so the queries that must skip them have something
    to skip.
    """
    path = tmp_path / "content.db"
    # `with sqlite3.connect(...)` commits but does not close -- the leak itself.
    with closing(sqlite3.connect(path)) as conn, conn:
        create_content_schema(conn)
        conn.executescript(SEED)
    return path


@pytest.fixture
def library(seeded_db_path: Path) -> ContentLibrary:
    """A read-write library over the seeded database."""
    return ContentLibrary(seeded_db_path)


@pytest.fixture
def read_only_library(seeded_db_path: Path) -> ContentLibrary:
    """A read-only library over the seeded database, as the app opens it."""
    return ContentLibrary(seeded_db_path, read_only=True)


@pytest.fixture
def unit() -> Unit:
    """A grammar unit."""
    return Unit(
        id=1, unit_number=1, title="Present Continuous", topic_name="Present Tenses"
    )


@pytest.fixture
def question() -> Question:
    """A closed question with a rule attached."""
    return Question(
        id=1,
        question_id="1",
        is_open_ended=False,
        section_letter="A",
        rule="Use present continuous for actions happening now",
        display_order=0,
    )


@pytest.fixture
def exercise(unit: Unit, question: Question) -> Exercise:
    """An exercise with two questions."""
    second = Question(id=2, question_id="2", section_letter="A", display_order=1)
    return Exercise(
        id=1,
        exercise_id="1.1",
        exercise_number=1,
        unit=unit,
        questions=(question, second),
    )


@pytest.fixture
def answers() -> list[QuestionAnswer]:
    """Two accepted answers for a question."""
    return [
        QuestionAnswer(
            short_answer="is doing", full_answer="He **is doing** his homework."
        ),
        QuestionAnswer(
            short_answer="'s doing", full_answer="He **'s doing** his homework."
        ),
    ]


@pytest.fixture
def topics() -> list[Topic]:
    """Two topics."""
    return [
        Topic(id=1, name="Present Tenses", unit_count=10),
        Topic(id=2, name="Past Tenses", unit_count=8),
    ]
