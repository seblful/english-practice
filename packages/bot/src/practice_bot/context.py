"""Dependency wiring for handlers."""

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
        """Return whether a user is the configured admin."""
        return self.admin_user_id is not None and user_id == self.admin_user_id

    def start_exercise(self, user_id: int, active: ActiveExercise) -> None:
        """Move a user onto a new exercise."""
        self.agents.start_exercise(user_id, active.exercise.id)
        self.sessions.start_exercise(user_id, active)

    def forget_user(self, user_id: int) -> None:
        """Drop everything held in memory for one user."""
        self.sessions.forget(user_id)
        self.agents.forget_user(user_id)


class BotContext(
    CallbackContext[ExtBot[None], dict[Any, Any], dict[Any, Any], dict[Any, Any]]
):
    """Callback context that exposes the application's dependencies."""

    @property
    def dependencies(self) -> BotDependencies:
        """Return the installed dependencies."""
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
        """Move a user onto a new exercise, session and transcripts together."""
        self.dependencies.start_exercise(user_id, active)

    def forget_user(self, user_id: int) -> None:
        """Drop everything held in memory for one user."""
        self.dependencies.forget_user(user_id)


CONTEXT_TYPES = ContextTypes(context=BotContext)


def install_dependencies(
    bot_data: dict[Any, Any], dependencies: BotDependencies
) -> None:
    """Make dependencies reachable from every handler's context."""
    bot_data[_DEPENDENCIES_KEY] = dependencies


def load_dependencies(bot_data: dict[Any, Any]) -> BotDependencies:
    """Return the dependencies installed in an application's ``bot_data``."""
    dependencies = bot_data.get(_DEPENDENCIES_KEY)
    if not isinstance(dependencies, BotDependencies):
        raise ConfigurationError(
            "bot dependencies are missing; build the application with "
            "practice_bot.app.build_application()"
        )
    return dependencies
