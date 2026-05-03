"""Shared fixtures for bot tests."""

from unittest.mock import AsyncMock, Mock

import pytest
from telegram import Update, User, Message, CallbackQuery


@pytest.fixture
def mock_user() -> Mock:
    """Create a mock Telegram user."""
    user = Mock(spec=User)
    user.id = 12345
    user.first_name = "Test"
    user.full_name = "Test"
    user.username = "testuser"
    return user


@pytest.fixture
def mock_message(mock_user) -> AsyncMock:
    """Create a mock Telegram message with async reply methods."""
    message = AsyncMock(spec=Message)
    message.text = "test message"
    message.reply_text = AsyncMock(return_value=None)
    message.reply_photo = AsyncMock(return_value=None)
    message.from_user = mock_user
    return message


@pytest.fixture
def mock_callback_query(mock_user, mock_message) -> AsyncMock:
    """Create a mock callback query."""
    query = AsyncMock(spec=CallbackQuery)
    query.data = "topic:random"
    query.from_user = mock_user
    query.message = mock_message
    query.answer = AsyncMock(return_value=None)
    return query


@pytest.fixture
def mock_update(mock_user, mock_message) -> Mock:
    """Create a mock Update for command/text messages."""
    update = Mock(spec=Update)
    update.effective_user = mock_user
    update.effective_chat = Mock()
    update.effective_chat.id = 12345
    update.message = mock_message
    update.callback_query = None
    return update


@pytest.fixture
def mock_callback_update(mock_user, mock_callback_query) -> Mock:
    """Create a mock Update for callback queries."""
    update = Mock(spec=Update)
    update.effective_user = mock_user
    update.effective_chat = Mock()
    update.effective_chat.id = 12345
    update.message = None
    update.callback_query = mock_callback_query
    return update


@pytest.fixture
def mock_context() -> Mock:
    """Create a mock context with bot."""
    context = Mock()
    context.bot = AsyncMock()
    context.bot.set_my_commands = AsyncMock(return_value=None)
    context.bot_data = {}
    context.user_data = {}
    return context


@pytest.fixture
def mock_repository() -> Mock:
    """Create a mock DatabaseRepository with default return values."""
    repo = Mock()

    repo.get_all_topics.return_value = [
        {"id": 1, "name": "Present Tenses", "unit_count": 10},
        {"id": 2, "name": "Past Tenses", "unit_count": 8},
    ]

    repo.get_topic_by_id.return_value = {"id": 1, "name": "Present Tenses"}

    repo.get_random_exercise.return_value = {
        "id": 1,
        "exercise_id": "1.1",
        "exercise_number": 1,
        "unit_id": 1,
        "unit_number": 1,
        "title": "Present Continuous",
    }

    repo.get_exercise_image.return_value = b"fake_image_bytes"

    repo.get_exercise_with_questions.return_value = {
        "id": 1,
        "exercise_id": "1.1",
        "exercise_number": 1,
        "unit_id": 1,
        "unit_number": 1,
        "title": "Present Continuous",
        "questions": [
            {
                "id": 1,
                "question_id": "1",
                "is_open_ended": False,
                "section_letter": "A",
                "rule": "Use present continuous for actions happening now",
                "display_order": 0,
                "answers": [
                    {"short_answer": "is doing", "full_answer": "He **is doing** his homework."},
                ],
            },
            {
                "id": 2,
                "question_id": "2",
                "is_open_ended": False,
                "section_letter": "A",
                "rule": "Use present continuous for temporary situations",
                "display_order": 1,
                "answers": [
                    {"short_answer": "are going", "full_answer": "They **are going** to school."},
                ],
            },
        ],
    }

    repo.get_all_answers.return_value = [
        Mock(short_answer="is doing", full_answer="He **is doing** his homework."),
    ]

    repo.get_rule.return_value = {
        "section_letter": "A",
        "rule": "Use present continuous for actions happening now",
    }

    repo.get_topic_for_question.return_value = "Present Tenses"

    # Auth mocks
    repo.get_user_auth_status = Mock(return_value=None)
    repo.add_user = Mock(return_value=None)
    repo.set_user_status = Mock(return_value=None)
    repo.get_pending_users = Mock(return_value=[])

    return repo


@pytest.fixture
def mock_agent_service() -> AsyncMock:
    """Create a mock AgentService."""
    service = AsyncMock()
    service.on_new_image = Mock(return_value=None)
    service.clear_all_history = Mock(return_value=None)
    return service


@pytest.fixture(autouse=True)
def patch_repository(monkeypatch, mock_repository) -> Mock:
    """Patch DatabaseRepository to return mock instance in all handlers."""
    monkeypatch.setattr(
        "src.english_practice.bot.handlers.DatabaseRepository",
        lambda *a, **kw: mock_repository,
    )
    monkeypatch.setattr(
        "src.english_practice.repositories.database.DatabaseRepository",
        lambda *a, **kw: mock_repository,
    )
    return mock_repository


@pytest.fixture(autouse=True)
def patch_agent_service(monkeypatch, mock_agent_service) -> AsyncMock:
    """Patch AgentService to return mock instance in all handlers."""
    monkeypatch.setattr(
        "src.english_practice.bot.handlers.AgentService",
        lambda *a, **kw: mock_agent_service,
    )
    return mock_agent_service


@pytest.fixture(autouse=True)
def reset_state_manager() -> None:
    """Reset state_manager between tests."""
    from src.english_practice.bot.states import state_manager
    state_manager.sessions.clear()


@pytest.fixture(autouse=True)
def reset_auth(monkeypatch) -> None:
    """Reset auth to disabled by default for all tests."""
    monkeypatch.setattr(
        "config.settings.settings.telegram.admin_user_id",
        None,
    )


@pytest.fixture
def patch_auth_enabled(monkeypatch) -> None:
    """Enable authorization with admin_user_id matching the mock user (12345)."""
    monkeypatch.setattr(
        "config.settings.settings.telegram.admin_user_id",
        12345,
    )


@pytest.fixture
def patch_auth_admin(monkeypatch) -> None:
    """Set admin_user_id to a different ID (not the mock user's) for testing admin-only commands."""
    monkeypatch.setattr(
        "config.settings.settings.telegram.admin_user_id",
        99999,
    )
