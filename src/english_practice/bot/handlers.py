"""Bot handlers for commands and messages."""

import logging
import re

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
from src.english_practice.bot.keyboards import (
    get_exercise_keyboard,
    get_new_exercise_keyboard,
    get_topic_keyboard,
)
from src.english_practice.bot.states import state_manager
from src.english_practice.repositories.database import DatabaseRepository
from src.english_practice.services.agent_service import AgentService

logger = logging.getLogger(__name__)


def _md_to_html(text: str) -> str:
    """Convert markdown bold (**text**) to HTML bold (<b>text</b>)."""
    return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")

    repository = DatabaseRepository()
    topics = repository.get_all_topics()

    welcome_text = (
        f"👋 Welcome to English Practice Bot, {user.first_name}!\n\n"
        "I'll help you practice English grammar with exercises from Murphy's book.\n\n"
        "Select a topic or choose 'Random from All Topics':"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_topic_keyboard(topics),
    )


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

    import random

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
        available_questions=[q["question_id"] for q in exercise_data["questions"]],
    )

    text = (
        f"Topic: {topic_name}\n\n"
        f"Answer question {question['question_id']} from the exercise below:"
    )

    message = update.message if update.message else update.callback_query.message

    await message.reply_text(text, parse_mode="HTML")

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
    elif action == "new_exercise":
        await query.message.reply_text(
            "Choose exercise type:",
            reply_markup=get_new_exercise_keyboard(),
        )


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

    text = (
        f"📖 <b>Unit Information</b>\n\n"
        f"🔢 Unit Number: <b>{exercise['unit_number']}</b>\n"
        f"📌 Title: <b>{exercise['title']}</b>\n\n"
        f"Exercise: {exercise['exercise_id']}"
    )

    await update.callback_query.message.reply_text(text, parse_mode="HTML")


async def handle_new_exercise_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle new exercise selection."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    session = state_manager.get_session(user_id)

    _, choice = query.data.split(":")

    if choice == "random":
        await send_new_exercise(update, context, user_id, None, "Random")
    elif choice == "same":
        topic_id = session.current_topic_id
        repository = DatabaseRepository()
        if topic_id:
            topic = repository.get_topic_by_id(topic_id)
            topic_name = topic["name"] if topic else "Same Topic"
        else:
            topic_name = "Random"
        await send_new_exercise(update, context, user_id, topic_id, topic_name)
    elif choice == "change":
        repository = DatabaseRepository()
        topics = repository.get_all_topics()
        await query.message.reply_text(
            "Select a topic:",
            reply_markup=get_topic_keyboard(topics),
        )


def _is_help_request(text: str) -> bool:
    """Check if the user is asking for help/assistance.

    Args:
        text: User message text.

    Returns:
        True if user is asking for help, False otherwise.
    """
    help_keywords = [
        "help",
        "explain",
        "why",
        "how",
        "what",
        "?",
        "don't understand",
        "dont understand",
        "confused",
        "can you",
        "could you",
        "please explain",
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in help_keywords)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages (answers to questions or help requests)."""
    user_id = update.effective_user.id
    session = state_manager.get_session(user_id)

    if not session.current_exercise_id:
        await update.message.reply_text(
            "👋 Welcome! Use /start to begin practicing English grammar."
        )
        return

    user_text = update.message.text.strip()

    # Check if user is asking for help
    if _is_help_request(user_text):
        try:
            agent_service = AgentService()
            result = agent_service.assist(
                user_id=user_id,
                image_path=session.current_exercise_path,
                question_number=session.current_question_id,
                user_input=user_text,
            )
            # Format structured assistant response with HTML conversion
            response_parts = [f"💬 {_md_to_html(result.answer)}"]
            if result.key_point:
                response_parts.append(f"🔑 <b>Key:</b> {_md_to_html(result.key_point)}")
            if result.tip:
                response_parts.append(f"💡 <b>Tip:</b> {_md_to_html(result.tip)}")
            response = "\n\n".join(response_parts)
            await update.message.reply_text(response, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Assistant agent error: {e}")
            await update.message.reply_text(
                "[X] Sorry, I couldn't process your question at the moment."
            )
        return

    # User is providing an answer
    question_number = extract_question_number(user_text)
    answer_text = extract_answer(user_text)

    if question_number:
        repository = DatabaseRepository()
        question = repository.get_question_by_number(
            session.current_exercise_id,
            question_number,
        )
        if question:
            target_question_id = question["id"]
            target_question_number = question["question_id"]
        else:
            await update.message.reply_text(
                f"[X] Question {question_number} not found in this exercise. "
                f"Available: {', '.join(session.available_questions)}"
            )
            return
    else:
        target_question_id = session.current_question_db_id
        target_question_number = session.current_question_id
        answer_text = user_text

    if not answer_text:
        await update.message.reply_text(
            "[?] Please provide an answer. "
            f"Your assigned question is: <b>{session.current_question_id}</b>",
            parse_mode="HTML",
        )
        return

    # Get correct answer from database
    repository = DatabaseRepository()
    _, correct_answer = repository.check_answer(
        target_question_id,
        answer_text,
    )

    try:
        agent_service = AgentService()
        # Step 1: Evaluate answer using agent
        evaluation = agent_service.evaluate_answer(
            image_path=session.current_exercise_path,
            question_number=target_question_number,
            user_input=answer_text,
            right_answer=correct_answer,
        )

        if evaluation.is_correct:
            # Step 2: Get full answer explanation
            full_answer = agent_service.get_full_answer(
                image_path=session.current_exercise_path,
                question_number=target_question_number,
                right_answer=correct_answer,
            )

            # Format response for correct answer with HTML conversion
            response = (
                f"✅ <b>Correct!</b>\n\n"
                f"📖 {_md_to_html(full_answer.sentence)}\n\n"
                f"🔑 <b>Key:</b> {_md_to_html(full_answer.key_point)}\n"
                f"💡 {_md_to_html(full_answer.why)}"
            )
            await update.message.reply_text(response, parse_mode="HTML")
        else:
            # Step 2: Get full answer explanation for incorrect answer
            full_answer = agent_service.get_full_answer(
                image_path=session.current_exercise_path,
                question_number=target_question_number,
                right_answer=correct_answer,
            )

            # Format response for incorrect answer with HTML conversion
            response = (
                f"❌ <b>Not quite</b>\n\n"
                f"📝 Your answer: <i>{answer_text}</i>\n"
                f"✅ Correct: <b>{correct_answer}</b>\n\n"
                f"📖 {_md_to_html(full_answer.sentence)}\n\n"
                f"🔑 <b>Key:</b> {_md_to_html(full_answer.key_point)}\n"
                f"💡 {_md_to_html(full_answer.why)}"
            )
            await update.message.reply_text(response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Agent error: {e}")
        await update.message.reply_text(
            "[X] Sorry, I couldn't evaluate your answer at the moment. "
            f"The correct answer was: {correct_answer}"
        )

    if question_number and question_number != session.current_question_id:
        await update.message.reply_text(
            f"\n[NOTE] Your assigned question is still: <b>{session.current_question_id}</b>",
            parse_mode="HTML",
        )


def extract_question_number(text: str) -> str | None:
    """Extract question number from text.

    Args:
        text: User message text.

    Returns:
        Question number or None.
    """
    patterns = [
        r"(?:question|q)[\s:]?(\d+[a-z]?)",
        r"(?:number|num|#)[\s:]?(\d+[a-z]?)",
        r"^[\s]*(\d+[a-z]?)[\s]*[.:\-]?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_answer(text: str) -> str:
    """Extract answer from text, removing question references.

    Args:
        text: User message text.

    Returns:
        Clean answer text.
    """
    patterns = [
        r"(?:question|q)[\s:]?\d+[a-z]?[\s]*[.:\-]?\s*",
        r"(?:number|num|#)\d+[a-z]?[\s]*[.:\-]?\s*",
        r"^\d+[a-z]?[\s]*[.:\-]?\s*",
    ]

    answer = text
    for pattern in patterns:
        answer = re.sub(pattern, "", answer, flags=re.IGNORECASE)

    return answer.strip()


start_handler = CommandHandler("start", start_command)
topic_handler = CallbackQueryHandler(
    handle_topic_selection,
    pattern="^topic:",
)
exercise_action_handler = CallbackQueryHandler(
    handle_exercise_action,
    pattern="^action:",
)
new_exercise_handler = CallbackQueryHandler(
    handle_new_exercise_selection,
    pattern="^new:",
)
message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    handle_message,
)
