"""Main entry point for Telegram English Practice Bot."""

import os
import logging
import sys

from telegram import MenuButtonCommands
from telegram.ext import Application

from config.logging import setup_logging
from config.settings import settings
from src.english_practice.bot.handlers import (
    admin_action_handler,
    exercise_action_handler,
    exercise_handler,
    message_handler,
    pending_handler,
    rule_handler,
    start_handler,
    topic_handler,
)


def setup_langsmith() -> None:
    """Setup LangSmith environment variables."""

    if settings.langsmith.api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith.api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith.project
        os.environ["LANGSMITH_TRACING"] = str(settings.langsmith.tracing).lower()


def validate_settings() -> bool:
    """Validate required settings are configured.

    Returns:
        True if all required settings are present.
    """
    errors = []

    if not settings.telegram.bot_token:
        errors.append("TELEGRAM_BOT_TOKEN is not set")

    provider = settings.llm.provider
    if provider == "dashscope" and not settings.llm.dashscope.api_key:
        errors.append("DASHSCOPE_API_KEY is not set")
    elif provider == "gemini" and not settings.llm.gemini.api_key:
        errors.append("GEMINI_API_KEY is not set")
    elif provider == "openrouter" and not settings.llm.openrouter.api_key:
        errors.append("OPENROUTER_API_KEY is not set")

    if settings.langsmith.tracing and not settings.langsmith.api_key:
        errors.append("LANGSMITH_API_KEY is required when tracing is enabled")

    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease add these to your .env file:")
        print("  TELEGRAM_BOT_TOKEN=your_token")
        print("  DASHSCOPE_API_KEY=your_key (if using dashscope)")
        print("  GEMINI_API_KEY=your_key (if using gemini)")
        print("  OPENROUTER_API_KEY=your_key (if using openrouter)")
        print("  LANGSMITH_API_KEY=your_key (optional if tracing=false)")
        print(f"\nCurrent provider: {provider}")
        return False

    return True


async def post_init(application: Application) -> None:
    """Set up bot commands menu after initialization."""
    await application.bot.set_my_commands(
        [
            ("start", "Start the bot"),
            ("exercise", "Get new exercise"),
            ("rule", "Toggle rule display"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def main() -> int:
    """Run the Telegram bot.

    Returns:
        Exit code.
    """
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting English Practice Bot...")

    if not validate_settings():
        return 1

    setup_langsmith()

    try:
        application = (
            Application.builder()
            .token(settings.telegram.bot_token)
            .connect_timeout(settings.telegram.connect_timeout)
            .read_timeout(settings.telegram.read_timeout)
            .write_timeout(settings.telegram.write_timeout)
            .pool_timeout(settings.telegram.pool_timeout)
            .post_init(post_init)
            .concurrent_updates(settings.telegram.concurrent_updates)
            .build()
        )

        application.add_handler(start_handler)
        application.add_handler(exercise_handler)
        application.add_handler(rule_handler)
        application.add_handler(pending_handler)
        application.add_handler(topic_handler)
        application.add_handler(exercise_action_handler)
        application.add_handler(admin_action_handler)
        application.add_handler(message_handler)

        logger.info("Bot started successfully!")
        logger.info("Press Ctrl+C to stop")

        application.run_polling(
            allowed_updates=settings.telegram.allowed_updates,
            close_loop=settings.telegram.close_loop,
        )

    except Exception as e:
        logger.error(f"Error running bot: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
