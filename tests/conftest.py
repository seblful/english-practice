"""Shared fixtures.

The bot's handlers take their collaborators from the context, so a test wires
mocks into :class:`BotDependencies` instead of patching module globals. The
session store is real: its behaviour is part of what the handler tests assert.
"""

import logging
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import structlog
from telegram import CallbackQuery, Message, Update, User

from english_practice.bot.context import BotContext, BotDependencies
from english_practice.bot.states import SessionStore
from english_practice.models.auth import PendingUser
from english_practice.models.book import Exercise, Question, QuestionAnswer, Topic, Unit
from english_practice.repositories.database import DatabaseRepository
from english_practice.services.agent_service import AgentService
from english_practice.settings import Settings

USER_ID = 12345
ADMIN_ID = 99999

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "database" / "schema.sql"
)


@pytest.fixture(autouse=True)
def _quiet_logging() -> None:
    """Drop application log records so test output stays readable.

    The code under test logs deliberately, including full tracebacks from the
    error handler; none of that belongs in pytest's captured output. This runs
    per test because the logging tests reconfigure structlog themselves.
    """
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.ReturnLoggerFactory(),
    )


# ----------------------------------------------------------------------
# Reading replies
# ----------------------------------------------------------------------


def replies(message: AsyncMock) -> list[str]:
    """Return the text of every reply sent to a message.

    Args:
        message: The mocked message the handler replied to.

    Returns:
        Each reply's text, in the order it was sent.
    """
    return [call.args[0] for call in message.reply_text.call_args_list]


def last_reply(message: AsyncMock) -> tuple[str, dict]:
    """Return the text and keyword arguments of the last reply.

    Args:
        message: The mocked message the handler replied to.

    Returns:
        The final reply's text and its keyword arguments.
    """
    call = message.reply_text.call_args
    return call.args[0], call.kwargs


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------


@pytest.fixture
def seeded_db_path(tmp_path: Path) -> Path:
    """Build a database from the project schema, with a little content.

    Using the real schema is deliberate: a column renamed in ``schema.sql``
    should break these tests rather than production. Exercise 2 deliberately
    has no questions, and topic 3 no units, so the queries that must skip them
    have something to skip.
    """
    path = tmp_path / "test.db"
    # `with sqlite3.connect(...)` commits but does not close, which is the very
    # leak the repository fixes -- so the fixture must not repeat it either.
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(
            """
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
        )
    return path


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------


@pytest.fixture
def tmp_env_file(tmp_path: Path) -> Path:
    """Create a temporary .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP__ENVIRONMENT=test\n")
    return env_file


@pytest.fixture
def test_settings(tmp_env_file: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings isolated from the host environment."""
    for key in list(os.environ):
        if key.startswith(("APP__", "LOGGING__")):
            monkeypatch.delenv(key, raising=False)
    return Settings(_env_file=tmp_env_file)


# ----------------------------------------------------------------------
# Domain fixtures
# ----------------------------------------------------------------------


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


# ----------------------------------------------------------------------
# Telegram fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def mock_user() -> Mock:
    """A Telegram user."""
    user = Mock(spec=User)
    user.id = USER_ID
    user.first_name = "Test"
    user.full_name = "Test User"
    user.username = "testuser"
    return user


@pytest.fixture
def mock_message(mock_user: Mock) -> AsyncMock:
    """A Telegram message with async reply methods."""
    message = AsyncMock(spec=Message)
    message.text = "is doing"
    message.from_user = mock_user
    return message


@pytest.fixture
def mock_update(mock_user: Mock, mock_message: AsyncMock) -> Mock:
    """An update carrying a text message."""
    update = Mock(spec=Update)
    update.update_id = 1
    update.effective_user = mock_user
    update.message = mock_message
    update.callback_query = None
    return update


@pytest.fixture
def mock_callback_query(mock_user: Mock, mock_message: AsyncMock) -> AsyncMock:
    """A pressed inline button."""
    query = AsyncMock(spec=CallbackQuery)
    query.data = "topic:random"
    query.from_user = mock_user
    query.message = mock_message
    return query


@pytest.fixture
def mock_callback_update(mock_user: Mock, mock_callback_query: AsyncMock) -> Mock:
    """An update carrying a callback query."""
    update = Mock(spec=Update)
    update.update_id = 2
    update.effective_user = mock_user
    update.message = None
    update.callback_query = mock_callback_query
    return update


# ----------------------------------------------------------------------
# Dependency fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def mock_repository(
    exercise: Exercise, answers: list[QuestionAnswer], topics: list[Topic]
) -> AsyncMock:
    """A repository whose queries succeed with the domain fixtures."""
    repository = AsyncMock(spec=DatabaseRepository)
    repository.list_topics.return_value = topics
    repository.get_topic.return_value = topics[0]
    repository.random_exercise.return_value = exercise
    repository.get_exercise_image.return_value = b"fake_image_bytes"
    repository.list_answers.return_value = answers
    repository.get_auth_status.return_value = None
    repository.list_pending_users.return_value = [
        PendingUser(telegram_id=111, full_name="Alice", telegram_username="alice"),
        PendingUser(telegram_id=222, full_name="Bob"),
    ]
    return repository


@pytest.fixture
def mock_agents() -> AsyncMock:
    """An agent service that grades everything correct."""
    agents = AsyncMock(spec=AgentService)
    agents.evaluate_answer.return_value = Mock(is_correct=True, answer_idx=[0])
    agents.assist.return_value = Mock(answer="Here is some **help**")
    return agents


@pytest.fixture
def sessions() -> SessionStore:
    """A real session store, empty for each test."""
    return SessionStore()


@pytest.fixture
def dependencies(
    mock_repository: AsyncMock, mock_agents: AsyncMock, sessions: SessionStore
) -> BotDependencies:
    """Dependencies with access control switched off."""
    return BotDependencies(
        repository=mock_repository,
        agents=mock_agents,
        sessions=sessions,
        admin_user_id=None,
    )


@pytest.fixture
def mock_context(dependencies: BotDependencies) -> Mock:
    """A handler context backed by the mock dependencies."""
    context = Mock(spec=BotContext)
    context.bot = AsyncMock()
    context.dependencies = dependencies
    context.repository = dependencies.repository
    context.agents = dependencies.agents
    context.sessions = dependencies.sessions
    return context


@pytest.fixture
def set_admin(mock_context: Mock) -> Callable[[int | None], None]:
    """Return a helper that switches access control on for a given admin ID."""

    def _set_admin(admin_user_id: int | None) -> None:
        mock_context.dependencies = replace(
            mock_context.dependencies, admin_user_id=admin_user_id
        )

    return _set_admin
