"""Tests for DatabaseRepository with in-memory SQLite."""

import sqlite3
from pathlib import Path

import pytest

from src.english_practice.repositories.database import DatabaseRepository


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY,
    unit_number INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    grammar_md_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY,
    exercise_id TEXT NOT NULL UNIQUE,
    unit_id INTEGER NOT NULL,
    exercise_number INTEGER NOT NULL,
    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exercise_images (
    id INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL UNIQUE,
    image_data BLOB NOT NULL,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    is_open_ended BOOLEAN DEFAULT 0,
    section_letter TEXT,
    rule TEXT,
    display_order INTEGER DEFAULT 0,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
    UNIQUE(exercise_id, question_id)
);

CREATE TABLE IF NOT EXISTS question_answers (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,
    short_answer TEXT NOT NULL,
    full_answer TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    UNIQUE(question_id, short_answer)
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_topic_id INTEGER,
    FOREIGN KEY (parent_topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS unit_topics (
    unit_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    PRIMARY KEY (unit_id, topic_id),
    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);
"""


def _build_db(db_path: Path) -> None:
    """Build a test database with schema and sample data."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

    conn.execute("INSERT INTO units (unit_number, title, grammar_md_path) VALUES (1, 'Present Continuous', 'grammar/1.md')")
    conn.execute("INSERT INTO units (unit_number, title, grammar_md_path) VALUES (2, 'Present Simple', 'grammar/2.md')")
    conn.execute("INSERT INTO exercises (exercise_id, unit_id, exercise_number) VALUES ('1.1', 1, 1)")
    conn.execute("INSERT INTO exercises (exercise_id, unit_id, exercise_number) VALUES ('1.2', 1, 2)")
    conn.execute("INSERT INTO exercises (exercise_id, unit_id, exercise_number) VALUES ('2.1', 2, 1)")
    conn.execute("INSERT INTO exercise_images (exercise_id, image_data) VALUES (1, X'010203')")
    conn.execute("""INSERT INTO questions (exercise_id, question_id, is_open_ended, section_letter, rule, display_order)
                    VALUES (1, '1', 0, 'A', 'Use for now', 0)""")
    conn.execute("""INSERT INTO questions (exercise_id, question_id, is_open_ended, section_letter, rule, display_order)
                    VALUES (1, '2', 0, 'A', 'Use for temp', 1)""")
    conn.execute("""INSERT INTO questions (exercise_id, question_id, is_open_ended, section_letter, rule, display_order)
                    VALUES (2, '1', 1, NULL, NULL, 0)""")
    conn.execute("""INSERT INTO question_answers (question_id, short_answer, full_answer)
                    VALUES (1, 'is doing', 'He **is doing** his homework.')""")
    conn.execute("""INSERT INTO question_answers (question_id, short_answer, full_answer)
                    VALUES (1, 'is making', 'He **is making** dinner.')""")
    conn.execute("""INSERT INTO question_answers (question_id, short_answer, full_answer)
                    VALUES (2, 'are going', 'They **are going** to school.')""")
    conn.execute("INSERT INTO topics (name) VALUES ('Present Tenses')")
    conn.execute("INSERT INTO topics (name) VALUES ('Past Tenses')")
    conn.execute("INSERT INTO unit_topics (unit_id, topic_id) VALUES (1, 1)")
    conn.execute("INSERT INTO unit_topics (unit_id, topic_id) VALUES (2, 1)")

    conn.commit()
    conn.close()


def _build_empty_db(db_path: Path) -> None:
    """Build an empty test database with just the schema."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@pytest.fixture
def empty_repo(tmp_path) -> DatabaseRepository:
    """Create a DatabaseRepository with empty schema."""
    db_path = tmp_path / "empty.db"
    _build_empty_db(db_path)
    return DatabaseRepository(db_path)


@pytest.fixture
def populated_repo(tmp_path) -> DatabaseRepository:
    """Create a DatabaseRepository with test data."""
    db_path = tmp_path / "test.db"
    _build_db(db_path)
    return DatabaseRepository(db_path)


class TestDatabaseRepositoryEmpty:
    """Tests with empty database."""

    def test_get_all_topics_empty(self, empty_repo) -> None:
        assert empty_repo.get_all_topics() == []

    def test_get_topic_by_id_nonexistent(self, empty_repo) -> None:
        assert empty_repo.get_topic_by_id(999) is None

    def test_get_random_exercise_empty(self, empty_repo) -> None:
        assert empty_repo.get_random_exercise() is None

    def test_get_random_exercise_with_topic_empty(self, empty_repo) -> None:
        assert empty_repo.get_random_exercise(topic_id=1) is None

    def test_get_exercise_image_nonexistent(self, empty_repo) -> None:
        assert empty_repo.get_exercise_image(999) is None

    def test_get_exercise_with_questions_nonexistent(self, empty_repo) -> None:
        assert empty_repo.get_exercise_with_questions(999) is None

    def test_get_all_answers_nonexistent(self, empty_repo) -> None:
        assert empty_repo.get_all_answers(999) == []

    def test_get_rule_nonexistent(self, empty_repo) -> None:
        assert empty_repo.get_rule(999) is None

    def test_get_topic_for_question_nonexistent(self, empty_repo) -> None:
        assert empty_repo.get_topic_for_question(999) is None


class TestDatabaseRepositoryPopulated:
    """Tests with populated database."""

    def test_get_all_topics(self, populated_repo) -> None:
        topics = populated_repo.get_all_topics()
        assert len(topics) == 2
        names = [t["name"] for t in topics]
        assert "Past Tenses" in names
        assert "Present Tenses" in names

    def test_get_all_topics_includes_unit_count(self, populated_repo) -> None:
        topics = populated_repo.get_all_topics()
        present = next(t for t in topics if t["name"] == "Present Tenses")
        assert present["unit_count"] == 2
        past = next(t for t in topics if t["name"] == "Past Tenses")
        assert past["unit_count"] == 0

    def test_get_topic_by_id_found(self, populated_repo) -> None:
        topic = populated_repo.get_topic_by_id(1)
        assert topic is not None
        assert topic["name"] == "Present Tenses"

    def test_get_topic_by_id_not_found(self, populated_repo) -> None:
        assert populated_repo.get_topic_by_id(999) is None

    def test_get_random_exercise_any(self, populated_repo) -> None:
        ex = populated_repo.get_random_exercise()
        assert ex is not None
        assert ex["exercise_id"] in ("1.1", "1.2", "2.1")

    def test_get_random_exercise_by_topic(self, populated_repo) -> None:
        ex = populated_repo.get_random_exercise(topic_id=1)
        assert ex is not None
        assert ex["unit_number"] in (1, 2)

    def test_get_random_exercise_by_nonexistent_topic(self, populated_repo) -> None:
        assert populated_repo.get_random_exercise(topic_id=999) is None

    def test_get_exercise_image_found(self, populated_repo) -> None:
        img = populated_repo.get_exercise_image(1)
        assert img == b"\x01\x02\x03"

    def test_get_exercise_image_not_found(self, populated_repo) -> None:
        img = populated_repo.get_exercise_image(2)
        assert img is None

    def test_get_exercise_with_questions_found(self, populated_repo) -> None:
        ex = populated_repo.get_exercise_with_questions(1)
        assert ex is not None
        assert ex["exercise_id"] == "1.1"
        assert len(ex["questions"]) == 2
        assert ex["questions"][0]["question_id"] == "1"
        assert len(ex["questions"][0]["answers"]) == 2
        assert ex["questions"][1]["question_id"] == "2"
        assert len(ex["questions"][1]["answers"]) == 1

    def test_get_exercise_with_questions_not_found(self, populated_repo) -> None:
        assert populated_repo.get_exercise_with_questions(999) is None

    def test_get_exercise_with_questions_open_ended(self, populated_repo) -> None:
        ex = populated_repo.get_exercise_with_questions(2)
        assert ex is not None
        assert len(ex["questions"]) == 1
        assert ex["questions"][0]["is_open_ended"] is True
        assert ex["questions"][0]["section_letter"] is None

    def test_get_all_answers_found(self, populated_repo) -> None:
        answers = populated_repo.get_all_answers(1)
        assert len(answers) == 2
        shorts = [a.short_answer for a in answers]
        assert "is doing" in shorts
        assert "is making" in shorts

    def test_get_all_answers_not_found(self, populated_repo) -> None:
        assert populated_repo.get_all_answers(999) == []

    def test_get_rule_found(self, populated_repo) -> None:
        rule = populated_repo.get_rule(1)
        assert rule is not None
        assert rule["section_letter"] == "A"
        assert rule["rule"] == "Use for now"

    def test_get_rule_not_found(self, populated_repo) -> None:
        assert populated_repo.get_rule(999) is None

    def test_get_topic_for_question_found(self, populated_repo) -> None:
        topic = populated_repo.get_topic_for_question(1)
        assert topic == "Present Tenses"

    def test_get_topic_for_question_not_found(self, populated_repo) -> None:
        assert populated_repo.get_topic_for_question(999) is None
