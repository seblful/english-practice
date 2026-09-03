"""Dependency wiring for handlers.

Handlers receive their collaborators through the context object instead of
constructing them. That is what lets one repository, one chat-model client and
one session store serve the whole process — and what lets a test hand a
handler a mock without patching module globals.
"""

from dataclasses import dataclass
from typing import Any

from practice_core.content import ContentLibrary
from practice_core.lesson import ActiveExercise
from practice_runtime.errors import ConfigurationError
from telegram.ext import CallbackContext, ContextTypes, ExtBot

from practice_bot.repositories.database import AuthRepository
from practice_bot.services.agent_service import AgentService
from practice_bot.states import SessionStore

_DEPENDENCIES_KEY = "dependencies"


@dataclass(frozen=True, slots=True)
class BotDependencies:
    """Everything the handlers need, built once per process."""

    content: ContentLibrary
    users: AuthRepository
    agents: AgentService
    sessions: SessionStore
    admin_user_id: int | None = None

    @property
    def access_control_enabled(self) -> bool:
        """Whether an admin is configured to gate access."""
        return self.admin_user_id is not None

    def is_admin(self, user_id: int) -> bool:
        """Return whether a user is the configured admin.

        Args:
            user_id: Telegram user ID.

        Returns:
            ``True`` when the user administers this bot.
        """
        return self.admin_user_id is not None and user_id == self.admin_user_id

    def start_exercise(self, user_id: int, active: ActiveExercise) -> None:
        """Move a user onto a new exercise.

        The session and the assistant transcripts are separate stores that must
        move together: leave the transcripts behind and the previous exercise's
        conversation bleeds into this one. Owning both here is what stops a
        handler from applying half of it.

        Args:
            user_id: The user's Telegram ID.
            active: The exercise the user just started.
        """
        self.agents.start_exercise(user_id, active.exercise.id)
        self.sessions.start_exercise(user_id, active)

    def forget_user(self, user_id: int) -> None:
        """Drop everything held in memory for one user.

        Args:
            user_id: The user's Telegram ID.
        """
        self.sessions.forget(user_id)
        self.agents.forget_user(user_id)


class BotContext(
    CallbackContext[ExtBot[None], dict[Any, Any], dict[Any, Any], dict[Any, Any]]
):
    """Callback context that exposes the application's dependencies."""

    @property
    def dependencies(self) -> BotDependencies:
        """Return the installed dependencies.

        Returns:
            The dependencies installed by :func:`install_dependencies`.

        Raises:
            ConfigurationError: If the application was built without them,
                which is a programming error rather than a runtime condition.
        """
        return load_dependencies(self.application.bot_data)

    @property
    def content(self) -> ContentLibrary:
        """Return the book."""
        return self.dependencies.content

    @property
    def users(self) -> AuthRepository:
        """Return the record of who may use the bot."""
        return self.dependencies.users

    @property
    def agents(self) -> AgentService:
        """Return the LLM agent service."""
        return self.dependencies.agents

    @property
    def sessions(self) -> SessionStore:
        """Return the user session store."""
        return self.dependencies.sessions

    def start_exercise(self, user_id: int, active: ActiveExercise) -> None:
        """Move a user onto a new exercise, session and transcripts together.

        Args:
            user_id: The user's Telegram ID.
            active: The exercise the user just started.
        """
        self.dependencies.start_exercise(user_id, active)

    def forget_user(self, user_id: int) -> None:
        """Drop everything held in memory for one user.

        Args:
            user_id: The user's Telegram ID.
        """
        self.dependencies.forget_user(user_id)


CONTEXT_TYPES = ContextTypes(context=BotContext)


def install_dependencies(
    bot_data: dict[Any, Any], dependencies: BotDependencies
) -> None:
    """Make dependencies reachable from every handler's context.

    Args:
        bot_data: The application's ``bot_data`` mapping.
        dependencies: The dependencies to install.
    """
    bot_data[_DEPENDENCIES_KEY] = dependencies


def load_dependencies(bot_data: dict[Any, Any]) -> BotDependencies:
    """Return the dependencies installed in an application's ``bot_data``.

    Handlers reach these through their context; this is for the two callers
    that have the application but no update — the startup hook, and a test.

    Args:
        bot_data: The application's ``bot_data`` mapping.

    Returns:
        The installed dependencies.

    Raises:
        ConfigurationError: If the application was built without them, which
            is a programming error rather than a runtime condition.
    """
    dependencies = bot_data.get(_DEPENDENCIES_KEY)
    if not isinstance(dependencies, BotDependencies):
        raise ConfigurationError(
            "bot dependencies are missing; build the application with "
            "practice_bot.app.build_application()"
        )
    return dependencies
