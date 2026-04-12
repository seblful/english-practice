"""Bot handlers for commands and messages."""

import logging
import random
from pathlib import Path
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import settings
from src.english_practice.bot.formatter import MessageFormatter
from src.english_practice.bot.keyboards import (
    get_exercise_keyboard,
    get_start_menu_keyboard,
    get_topic_keyboard,
)
from src.english_practice.bot.states import state_manager
from src.english_practice.repositories.database import DatabaseRepository
from src.english_practice.services.agent_service import AgentService

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")

    session = state_manager.get_session(user.id)
    has_previous_topic = session.current_topic_id is not None

    await context.bot.set_my_commands(
        [
            ("start", "Start the bot"),
            ("exercise", "Get new exercise"),
            ("rule", "Toggle rule display"),
        ]
    )

    welcome_text = (
        f"👋 Welcome to Random Murphy's English Grammar, {user.first_name}!\n\n"
        "I'll help you practice English grammar with exercises from Murphy's book.\n\n"
        "Choose an option:"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_start_menu_keyboard(has_previous_topic),
    )


async def exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /exercise command."""
    user = update.effective_user
    session = state_manager.get_session(user.id)
    has_previous_topic = session.current_topic_id is not None

    await update.message.reply_text(
        "Choose an option:",
        reply_markup=get_start_menu_keyboard(has_previous_topic),
    )


async def rule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rule command to toggle rule display."""
    user = update.effective_user
    new_value = state_manager.toggle_show_rule(user.id)
    status = "enabled ✅" if new_value else "disabled ❌"
    await update.message.reply_text(f"📋 Rule display is now {status}.")


async def handle_topic_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle topic selection callback."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    callback_data = query.data

    _, topic_id = callback_data.split(":")

    if topic_id == "new_topic":
        repository = DatabaseRepository()
        topics = repository.get_all_topics()
        await query.message.reply_text(
            "Select a topic:",
            reply_markup=get_topic_keyboard(topics),
        )
        return

    if topic_id == "same":
        session = state_manager.get_session(user_id)
        topic_id = session.current_topic_id
        if topic_id:
            repository = DatabaseRepository()
            topic = repository.get_topic_by_id(topic_id)
            topic_name = topic["name"] if topic else "Same Topic"
        else:
            topic_name = "Random"
        await send_new_exercise(update, context, user_id, topic_id, topic_name)
        return

    repository = DatabaseRepository()
    if topic_id == "random":
        topic_id = None
        topic_name = "Random"
    else:
        topic_id = int(topic_id)
        topic = repository.get_topic_by_id(topic_id)
        topic_name = topic["name"] if topic else "Unknown"

    await send_new_exercise(update, context, user_id, topic_id, topic_name)


async def send_new_exercise(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    topic_id: int | None,
    topic_name: str,
) -> None:
    """Send new exercise to user."""
    repository = DatabaseRepository()
    exercise = repository.get_random_exercise(topic_id)

    if not exercise:
        message = update.message if update.message else update.callback_query.message
        await message.reply_text(
            "[X] No exercises found for this topic. Please try another."
        )
        return

    exercise_data = repository.get_exercise_with_questions(exercise["id"])

    if not exercise_data or not exercise_data["questions"]:
        message = update.message if update.message else update.callback_query.message
        await message.reply_text("[X] Exercise has no questions. Trying another...")
        await send_new_exercise(update, context, user_id, topic_id, topic_name)
        return

    question = random.choice(exercise_data["questions"])

    image_path = Path(exercise["image_path"])
    if not image_path.is_absolute():
        image_path = settings.paths.content_dir / image_path

    AgentService().on_new_image(user_id, image_path)

    state_manager.set_exercise(
        user_id=user_id,
        exercise_id=exercise["id"],
        exercise_path=image_path,
        question_id=question["question_id"],
        question_db_id=question["id"],
        topic_id=topic_id,
        topic_name=topic_name,
        unit_number=exercise["unit_number"],
        available_questions=[q["question_id"] for q in exercise_data["questions"]],
    )

    message = update.message if update.message else update.callback_query.message

    # Send topic message
    await message.reply_text(
        MessageFormatter.format_topic(topic_name), parse_mode="HTML"
    )

    # Send question prompt message
    await message.reply_text(
        MessageFormatter.format_question_prompt(question["question_id"]),
        parse_mode="HTML",
    )

    # Send exercise image
    with open(image_path, "rb") as photo:
        await message.reply_photo(
            photo=photo,
            reply_markup=get_exercise_keyboard(),
        )


async def handle_exercise_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle exercise action buttons."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    session = state_manager.get_session(user_id)

    if not session.current_exercise_id:
        await query.message.reply_text(
            "[X] No active exercise. Use /start to select a topic."
        )
        return

    _, action = query.data.split(":")

    if action == "show_unit":
        await show_unit_info(update, context, user_id)


async def show_unit_info(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> None:
    """Show unit information."""
    repository = DatabaseRepository()
    session = state_manager.get_session(user_id)

    exercise = repository.get_exercise_with_questions(session.current_exercise_id)

    if not exercise:
        await update.callback_query.message.reply_text(
            "[X] Could not retrieve unit information."
        )
        return

    state_manager.mark_unit_shown(user_id)

    text = MessageFormatter.format_unit_info(
        unit_number=exercise["unit_number"],
        title=exercise["title"],
        exercise_id=exercise["exercise_id"],
    )

    await update.callback_query.message.reply_text(text, parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages (answers to questions or follow-up questions)."""
    user_id = update.effective_user.id
    session = state_manager.get_session(user_id)

    if not session.current_exercise_id:
        await update.message.reply_text(
            "👋 Welcome! Use /start to begin practicing English grammar."
        )
        return

    user_text = update.message.text.strip()

    # If already answered, treat as follow-up question for assistant
    if session.answered:
        try:
            agent_service = AgentService()
            result = await agent_service.assist(
                user_id=user_id,
                image_path=session.current_exercise_path,
                question_number=session.current_question_id,
                user_input=user_text,
                topic_name=session.current_topic_name or "Random",
            )
            response = MessageFormatter.format_assistant_answer(result.answer)
            await update.message.reply_text(response, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Assistant error: {e}")
            await update.message.reply_text(
                "[X] Sorry, I couldn't process your question at the moment."
            )
        return

    # User is providing an answer
    answer_text = user_text

    target_question_id = session.current_question_db_id
    target_question_number = session.current_question_id

    repository = DatabaseRepository()

    try:
        agent_service = AgentService()

        topic_name = session.current_topic_name or "Random"

        # Get full answers and rule from database
        all_answers = repository.get_all_answers(target_question_id)
        rule_data = repository.get_rule(target_question_id)

        first_correct_answer = all_answers[0].short_answer if all_answers else ""
        first_full_answer = all_answers[0].full_answer if all_answers else ""

        # Evaluate answer using agent
        evaluation = await agent_service.evaluate_answer(
            image_path=session.current_exercise_path,
            question_number=target_question_number,
            user_input=answer_text,
            correct_answer=first_correct_answer,
            full_answer=first_full_answer,
            topic_name=topic_name,
        )

        state_manager.mark_answered(user_id)

        # Send evaluation message
        eval_msg = MessageFormatter.format_evaluation(
            evaluation.is_correct, answer_text, first_correct_answer
        )
        await update.message.reply_text(eval_msg, parse_mode="HTML")

        # Send all full answer messages
        for answer in all_answers:
            full_answer_msg = MessageFormatter.format_full_answer(answer.full_answer)
            await update.message.reply_text(full_answer_msg, parse_mode="HTML")

        # Send rule message if available and enabled
        if rule_data and session.show_rule:
            rule_msg = MessageFormatter.format_rule(
                session.current_unit_number,
                rule_data["section_letter"],
                rule_data["rule"],
            )
            await update.message.reply_text(rule_msg, parse_mode="HTML")

        # Send new exercise options
        await update.message.reply_text(
            "Choose next exercise:",
            reply_markup=get_start_menu_keyboard(session.current_topic_id is not None),
        )

    except Exception as e:
        logger.error(f"Agent error: {e}")
        await update.message.reply_text(
            "[X] Sorry, I couldn't evaluate your answer at the moment."
        )


start_handler = CommandHandler("start", start_command)
exercise_handler = CommandHandler("exercise", exercise_command)
rule_handler = CommandHandler("rule", rule_command)
topic_handler = CallbackQueryHandler(
    handle_topic_selection,
    pattern="^topic:",
)
exercise_action_handler = CallbackQueryHandler(
    handle_exercise_action,
    pattern="^action:",
)
message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    handle_message,
)
