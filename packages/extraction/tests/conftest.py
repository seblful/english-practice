"""Shared fixtures for the pipeline tests.

Nothing here reaches a provider, opens the real book, or writes into the
repository's ``data/`` tree: the agents are handed in, the PDFs are built in a
temp directory, and the content layout is rooted at ``tmp_path``.
"""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import structlog
from practice_core.schema import create_content_schema
from practice_runtime.settings import PathSettings, settings_env_vars

from practice_extraction.settings import Settings


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the developer's own environment from every test.

    Each settings group is its own ``BaseSettings`` reading ``os.environ``
    through its prefix, so ``Settings(_env_file=...)`` does not isolate them --
    an exported ``OCR_API_KEY`` or ``PATHS_DATABASE_PATH`` would otherwise
    decide the outcome of a test that never mentions it.
    """
    for name in settings_env_vars(Settings):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _quiet_logging() -> None:
    """Drop application log records so test output stays readable."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.ReturnLoggerFactory(),
    )


def extraction_paths(root: Path) -> PathSettings:
    """Return a content layout rooted at ``root``, with the directories made.

    Every directory is passed explicitly: ``PathSettings`` computes its
    defaults at class definition, so setting ``content_dir`` alone would leave
    the others pointing at the real ``data/`` tree.

    Args:
        root: The scratch directory to root the layout at.

    Returns:
        The layout, with the directories the stages write into created.
    """
    content_dir = root / "content"
    paths = PathSettings(
        content_dir=content_dir,
        metadata_dir=content_dir / "metadata",
        exercises_dir=content_dir / "exercises",
        grammar_md_dir=content_dir / "grammar",
        database_path=content_dir / "english_practice.db",
    )
    for directory in (
        paths.metadata_dir,
        paths.exercises_dir,
        paths.grammar_md_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


@pytest.fixture
def paths(tmp_path: Path) -> PathSettings:
    """A content layout in a scratch directory."""
    return extraction_paths(tmp_path)


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
VALUES (1, X'89504E47');

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
    """Build a database from the shared schema, with a little content.

    The schema is `practice-core`'s, the same one ``populate`` builds from, so
    a column renamed there breaks these tests rather than production. Exercise
    2 deliberately has no questions and topic 3 no units, so the checks that
    must report them have something to find.
    """
    path = tmp_path / "test.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        create_content_schema(conn)
        conn.executescript(SEED)
    return path
