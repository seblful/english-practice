"""Application assembly: build the bot, wire its dependencies, run it.

This is the only place that knows how the pieces fit together, which is what
lets everything else — handlers, services, repository — stay unaware of how it
was constructed.
"""

import os
from datetime import timedelta
from typing import Any

from telegram import MenuButtonCommands
from telegram.ext import Application

from english_practice.bot import commands
from english_practice.bot.context import (
    CONTEXT_TYPES,
    BotContext,
    BotDependencies,
    install_dependencies,
)
from english_practice.bot.handlers import build_handlers, report_error
from english_practice.bot.states import SessionStore
from english_practice.errors import ConfigurationError
from english_practice.logging import get_logger
from english_practice.repositories.database import DatabaseRepository
from english_practice.services.agent_service import AgentService
from english_practice.settings import Settings, get_settings, secret_value

logger = get_logger(__name__)

BotApplication = Application[Any, BotContext, Any, Any, Any, Any]


def configure_tracing(settings: Settings) -> None:
    """Export the LangSmith variables its SDK reads from the environment.

    Args:
        settings: The application settings.
    """
    api_key = secret_value(settings.langsmith.api_key)
    if api_key is None:
        return

    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith.project
    os.environ["LANGSMITH_TRACING"] = str(settings.langsmith.tracing).lower()
    logger.info(
        "tracing_configured",
        project=settings.langsmith.project,
        enabled=settings.langsmith.tracing,
    )


def build_dependencies(settings: Settings) -> BotDependencies:
    """Construct the collaborators shared by every handler.

    Args:
        settings: The application settings.

    Returns:
        One repository, one agent service and one session store for the
        process.
    """
    return BotDependencies(
        repository=DatabaseRepository(settings.paths.database_path),
        agents=AgentService(max_history_messages=settings.bot.max_history_messages),
        sessions=SessionStore(
            idle_ttl=timedelta(minutes=settings.bot.session_idle_ttl_minutes)
        ),
        admin_user_id=settings.telegram.admin_user_id,
    )


async def _register_command_menu(application: BotApplication) -> None:
    """Publish the command menu once the bot is initialised.

    Args:
        application: The running application.
    """
    await application.bot.set_my_commands(commands.menu())
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def build_application(
    settings: Settings | None = None,
    dependencies: BotDependencies | None = None,
) -> BotApplication:
    """Build a ready-to-run application.

    Args:
        settings: The application settings. Defaults to the process settings.
        dependencies: Pre-built dependencies, for tests. Built from settings
            when omitted.

    Returns:
        The application, with handlers and dependencies installed.

    Raises:
        ConfigurationError: If a required setting is missing. Failing here
            keeps a half-configured bot from starting and then failing on the
            first user who says hello.
    """
    settings = settings or get_settings()

    problems = settings.missing_required()
    if problems:
        raise ConfigurationError(
            "cannot start the bot:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )

    configure_tracing(settings)

    token = secret_value(settings.telegram.bot_token)
    if token is None:  # pragma: no cover - missing_required rejects this above
        raise ConfigurationError("TELEGRAM_BOT_TOKEN is not set")

    telegram = settings.telegram
    application: BotApplication = (
        Application.builder()
        .token(token)
        .context_types(CONTEXT_TYPES)
        .connect_timeout(telegram.connect_timeout)
        .read_timeout(telegram.read_timeout)
        .write_timeout(telegram.write_timeout)
        .pool_timeout(telegram.pool_timeout)
        .concurrent_updates(telegram.concurrent_updates)
        .post_init(_register_command_menu)
        .build()
    )

    install_dependencies(
        application.bot_data, dependencies or build_dependencies(settings)
    )
    application.add_handlers(build_handlers())
    application.add_error_handler(report_error)

    return application


def run(settings: Settings | None = None) -> None:
    """Run the bot until interrupted.

    Args:
        settings: The application settings. Defaults to the process settings.

    Raises:
        ConfigurationError: If a required setting is missing.
    """
    settings = settings or get_settings()
    application = build_application(settings)

    logger.info(
        "bot_starting",
        environment=settings.app.environment,
        provider=settings.llm.provider,
        access_control=settings.telegram.admin_user_id is not None,
    )
    application.run_polling(
        allowed_updates=settings.telegram.allowed_updates,
        close_loop=settings.telegram.close_loop,
    )
    logger.info("bot_stopped")
