"""Main entry point for Telegram English Practice Bot."""

import logging
import sys

from pathlib import Path
from telegram import Update
from telegram.ext import Application

from config.logging import setup_logging
from config.settings import settings
from src.english_practice.bot.handlers import (
    exercise_action_handler,
    message_handler,
    new_exercise_handler,
    start_handler,
    topic_handler,
)


def setup_langsmith() -> None:
    """Setup LangSmith environment variables."""
    import os

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

    if not settings.qwen.api_key:
        errors.append("QWEN_API_KEY is not set")

    if settings.langsmith.tracing and not settings.langsmith.api_key:
        errors.append("LANGSMITH_API_KEY is required when tracing is enabled")

    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease add these to your .env file:")
        print("  TELEGRAM_BOT_TOKEN=your_token")
        print("  QWEN_API_KEY=your_key")
        print("  LANGSMITH_API_KEY=your_key (optional if tracing=false)")
        return False

    return True


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
        application = Application.builder().token(
            settings.telegram.bot_token
        ).build()

        application.add_handler(start_handler)
        application.add_handler(topic_handler)
        application.add_handler(exercise_action_handler)
        application.add_handler(new_exercise_handler)
        application.add_handler(message_handler)

        logger.info("Bot started successfully!")
        logger.info("Press Ctrl+C to stop")

        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Error running bot: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
