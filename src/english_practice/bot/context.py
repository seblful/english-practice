"""Dependency wiring for handlers.

Handlers receive their collaborators through the context object instead of
constructing them. That is what lets one repository, one chat-model client and
one session store serve the whole process — and what lets a test hand a
handler a mock without patching module globals.
"""

from dataclasses import dataclass
from typing import Any

from telegram.ext import CallbackContext, ContextTypes, ExtBot

from english_practice.bot.states import SessionStore
from english_practice.errors import ConfigurationError
from english_practice.repositories.database import DatabaseRepository
from english_practice.services.agent_service import AgentService

_DEPENDENCIES_KEY = "dependencies"


@dataclass(frozen=True, slots=True)
class BotDependencies:
    """Everything the handlers need, built once per process."""

    repository: DatabaseRepository
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
        dependencies = self.application.bot_data.get(_DEPENDENCIES_KEY)
        if not isinstance(dependencies, BotDependencies):
            raise ConfigurationError(
                "bot dependencies are missing; build the application with "
                "english_practice.bot.app.build_application()"
            )
        return dependencies

    @property
    def repository(self) -> DatabaseRepository:
        """Return the content and authorization repository."""
        return self.dependencies.repository

    @property
    def agents(self) -> AgentService:
        """Return the LLM agent service."""
        return self.dependencies.agents

    @property
    def sessions(self) -> SessionStore:
        """Return the user session store."""
        return self.dependencies.sessions


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
