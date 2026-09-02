"""Bot handlers for commands and messages."""

import io
import logging
import random

from telegram import CallbackQuery, Message, Update, User
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from english_practice.bot.formatter import MessageFormatter
from english_practice.bot.keyboards import (
    get_admin_pending_keyboard,
    get_admin_user_keyboard,
    get_exercise_keyboard,
    get_start_menu_keyboard,
    get_topic_keyboard,
)
from english_practice.bot.states import UserSession, state_manager
from english_practice.repositories.database import DatabaseRepository
from english_practice.services.agent_service import AgentService
from english_practice.settings import settings

logger = logging.getLogger(__name__)


def _get_target(update: Update) -> Message | None:
    """Get the message target for replying, regardless of update type."""
    if update.message is not None:
        return update.message
    query_message = update.callback_query.message if update.callback_query else None
    # CallbackQuery.message may be an InaccessibleMessage, which cannot be replied to.
    if isinstance(query_message, Message):
        return query_message
    return None


def _require_user(update: Update) -> User:
    """Return the user behind an update.

    Args:
        update: The incoming update.

    Returns:
        The effective user.

    Raises:
        ValueError: If the update carries no user, which the registered
            handlers are never invoked for.
    """
    user = update.effective_user
    if user is None:
        raise ValueError("Update carries no effective user")
    return user


def _require_message(update: Update) -> Message:
    """Return the message to reply to.

    Args:
        update: The incoming update.

    Returns:
        The message that replies should be attached to.

    Raises:
        ValueError: If the update carries no replyable message.
    """
    message = _get_target(update)
    if message is None:
        raise ValueError("Update carries no message to reply to")
    return message


def _require_query(update: Update) -> CallbackQuery:
    """Return the callback query behind an update.

    Args:
        update: The incoming update.

    Returns:
        The callback query.

    Raises:
        ValueError: If the update is not a callback query.
    """
    query = update.callback_query
    if query is None:
        raise ValueError("Update carries no callback query")
    return query


async def _check_authorization(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Check if user is authorized. Replies and returns False if not allowed."""
    user = _require_user(update)

    if settings.telegram.admin_user_id is None:
        return True

    if user.id == settings.telegram.admin_user_id:
        return True

    repository = DatabaseRepository()
    status = repository.get_user_auth_status(user.id)

    if status == "approved":
        return True

    target = _get_target(update)
    if target is None:
        return False

    if status in (None, "rejected"):
        if status is None:
            repository.add_user(user.id, user.full_name or "Unknown", user.username)
        else:
            repository.reset_user_to_pending(
                user.id, user.full_name or "Unknown", user.username
            )
        await target.reply_text(
            "⏳ Your request has been sent to the admin for approval."
        )
        if settings.telegram.admin_user_id:
            mention = f"@{user.username}" if user.username else "No username"
            await context.bot.send_message(
                chat_id=settings.telegram.admin_user_id,
                text=(
                    f"👤 <b>New user requested access</b>\n"
                    f"Name: {user.full_name or 'Unknown'}\n"
                    f"Username: {mention}\n"
                    f"ID: <code>{user.id}</code>"
                ),
                parse_mode="HTML",
                reply_markup=get_admin_user_keyboard(user.id),
            )
        return False

    await target.reply_text(
        "⏳ Your request is still pending. "
        "Please wait for the admin to approve your access."
    )
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not await _check_authorization(update, context):
        return

    user = _require_user(update)
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

    await _require_message(update).reply_text(
        welcome_text,
        reply_markup=get_start_menu_keyboard(has_previous_topic),
    )


async def exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /exercise command."""
    if not await _check_authorization(update, context):
        return

    user = _require_user(update)
    session = state_manager.get_session(user.id)
    has_previous_topic = session.current_topic_id is not None

    await _require_message(update).reply_text(
        "Choose an option:",
        reply_markup=get_start_menu_keyboard(has_previous_topic),
    )


async def rule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rule command to toggle rule display."""
    if not await _check_authorization(update, context):
        return

    user = _require_user(update)
    new_value = state_manager.toggle_show_rule(user.id)
    status = "enabled ✅" if new_value else "disabled ❌"
    await _require_message(update).reply_text(f"📋 Rule display is now {status}.")


async def handle_topic_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle topic selection callback."""
    query = _require_query(update)
    await query.answer()

    if not await _check_authorization(update, context):
        return

    user_id = _require_user(update).id
    callback_data = query.data or ""

    _, topic_id = callback_data.split(":")

    if topic_id == "new_topic":
        repository = DatabaseRepository()
        topics = repository.get_all_topics()
        await _require_message(update).reply_text(
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
        message = _require_message(update)
        await message.reply_text(
            "[X] No exercises found for this topic. Please try another."
        )
        return

    exercise_data = repository.get_exercise_with_questions(exercise["id"])

    if not exercise_data or not exercise_data["questions"]:
        message = _require_message(update)
        await message.reply_text("[X] Exercise has no questions. Trying another...")
        await send_new_exercise(update, context, user_id, topic_id, topic_name)
        return

    question = random.choice(exercise_data["questions"])

    image_data = repository.get_exercise_image(exercise["id"])

    AgentService().on_new_image(user_id, exercise["id"])

    state_manager.set_exercise(
        user_id=user_id,
        exercise_id=exercise["id"],
        question_id=question["question_id"],
        question_db_id=question["id"],
        topic_id=topic_id,
        topic_name=topic_name,
        unit_number=exercise["unit_number"],
        available_questions=[q["question_id"] for q in exercise_data["questions"]],
        is_open_ended=question["is_open_ended"],
    )

    message = _require_message(update)

    # Send topic message
    await message.reply_text(
        MessageFormatter.format_topic(topic_name), parse_mode="HTML"
    )

    # Send question prompt message
    await message.reply_text(
        MessageFormatter.format_question_prompt(question["question_id"]),
        parse_mode="HTML",
    )

    # Send exercise image from database
    if image_data:
        await message.reply_photo(
            photo=io.BytesIO(image_data),
            reply_markup=get_exercise_keyboard(),
        )
    else:
        await message.reply_text(
            "[X] Exercise image not found in database.",
            reply_markup=get_exercise_keyboard(),
        )


async def handle_exercise_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle exercise action buttons."""
    query = _require_query(update)
    await query.answer()

    if not await _check_authorization(update, context):
        return

    user_id = _require_user(update).id
    session = state_manager.get_session(user_id)

    if not session.current_exercise_id:
        await _require_message(update).reply_text(
            "[X] No active exercise. Use /start to select a topic."
        )
        return

    _, action = (query.data or "").split(":")

    if action == "show_unit":
        await show_unit_info(update, user_id)


async def show_unit_info(
    update: Update,
    user_id: int,
) -> None:
    """Show unit information."""
    repository = DatabaseRepository()
    session = state_manager.get_session(user_id)
    exercise_id = session.current_exercise_id

    exercise = (
        repository.get_exercise_with_questions(exercise_id)
        if exercise_id is not None
        else None
    )

    if not exercise:
        await _require_message(update).reply_text(
            "[X] Could not retrieve unit information."
        )
        return

    state_manager.mark_unit_shown(user_id)

    text = MessageFormatter.format_unit_info(
        unit_number=exercise["unit_number"],
        title=exercise["title"],
    )

    await _require_message(update).reply_text(text, parse_mode="HTML")


async def _handle_followup_question(
    message: Message,
    user_id: int,
    image_data: bytes | None,
    user_text: str,
    question_number: str,
    topic_name: str,
    exercise_id: int,
) -> None:
    """Answer a follow-up question about an already-answered exercise."""
    try:
        agent_service = AgentService()
        result = await agent_service.assist(
            user_id=user_id,
            image_data=image_data,
            question_number=question_number,
            user_input=user_text,
            topic_name=topic_name,
            exercise_id=exercise_id,
        )
        response = MessageFormatter.format_assistant_answer(result.answer)
        await message.reply_text(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Assistant error: {e}")
        await message.reply_text(
            "[X] Sorry, I couldn't process your question at the moment."
        )


async def _send_first_answers(
    message: Message, short_answers: list[str], full_answers: list[str]
) -> None:
    """Send the first known answer — the fallback when nothing matched."""
    if short_answers:
        await message.reply_text(
            MessageFormatter.format_short_answer(short_answers[0]),
            parse_mode="HTML",
        )
    if full_answers:
        await message.reply_text(
            MessageFormatter.format_full_answer(full_answers[0]),
            parse_mode="HTML",
        )


async def _send_matched_answers(
    message: Message,
    short_answers: list[str],
    full_answers: list[str],
    matched_indexes: list[int],
) -> None:
    """Send the answers the evaluation matched, or the first one if none did."""
    if not matched_indexes:
        await _send_first_answers(message, short_answers, full_answers)
        return

    matched_short = [
        short_answers[i] for i in matched_indexes if i < len(short_answers)
    ]
    matched_full = [full_answers[i] for i in matched_indexes if i < len(full_answers)]
    await message.reply_text(
        MessageFormatter.format_short_answers(matched_short),
        parse_mode="HTML",
    )
    if matched_full:
        await message.reply_text(
            MessageFormatter.format_full_answers(matched_full),
            parse_mode="HTML",
        )


async def _send_rule_if_enabled(
    message: Message, session: UserSession, rule_data: dict | None
) -> None:
    """Send the grammar rule when the session has rule display enabled."""
    unit_number = session.current_unit_number
    if not (rule_data and session.show_rule) or unit_number is None:
        return
    rule_msg = MessageFormatter.format_rule(
        unit_number,
        rule_data["section_letter"],
        rule_data["rule"],
    )
    await message.reply_text(rule_msg, parse_mode="HTML")


async def _send_next_exercise_prompt(message: Message, session: UserSession) -> None:
    """Offer the next exercise."""
    await message.reply_text(
        "Choose next exercise:",
        reply_markup=get_start_menu_keyboard(session.current_topic_id is not None),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user messages (answers to questions or follow-up questions)."""
    if not await _check_authorization(update, context):
        return

    user_id = _require_user(update).id
    session = state_manager.get_session(user_id)
    message = _require_message(update)

    # set_exercise() populates the exercise, question and unit fields together,
    # so any one of them being unset means there is no exercise in progress.
    exercise_id = session.current_exercise_id
    target_question_id = session.current_question_db_id
    target_question_number = session.current_question_id
    if not exercise_id or target_question_id is None or target_question_number is None:
        await message.reply_text(
            "👋 Welcome! Use /start to begin practicing English grammar."
        )
        return

    user_text = (message.text or "").strip()

    repository = DatabaseRepository()
    image_data = repository.get_exercise_image(exercise_id)

    # If already answered, treat as follow-up question for assistant
    if session.answered:
        await _handle_followup_question(
            message,
            user_id,
            image_data,
            user_text,
            question_number=target_question_number,
            topic_name=session.current_topic_name or "Random",
            exercise_id=exercise_id,
        )
        return

    # User is providing an answer
    answer_text = user_text

    is_open_ended = session.current_is_open_ended

    # Get all answers from database (outside try so available on error)
    all_answers = repository.get_all_answers(target_question_id)
    rule_data = repository.get_rule(target_question_id)
    rule_text = rule_data["rule"] if rule_data else None
    topic_name = repository.get_topic_for_question(target_question_id) or "Random"
    short_answers = [a.short_answer for a in all_answers]
    full_answers = [a.full_answer for a in all_answers]

    try:
        agent_service = AgentService()

        # Evaluate answer using agent
        evaluation = await agent_service.evaluate_answer(
            image_data=image_data,
            question_number=target_question_number,
            user_input=answer_text,
            short_answers=short_answers,
            full_answers=full_answers,
            is_open_ended=is_open_ended,
            topic_name=topic_name,
            rule=rule_text,
        )

        state_manager.mark_answered(user_id)

        feedback = MessageFormatter.format_evaluation(evaluation.is_correct)
        await message.reply_text(feedback, parse_mode="HTML")

        matched_indexes = evaluation.answer_idx

        await _send_matched_answers(
            message, short_answers, full_answers, matched_indexes
        )
        await _send_rule_if_enabled(message, session, rule_data)
        await _send_next_exercise_prompt(message, session)

    except Exception as e:
        logger.error(f"Agent error: {e}")
        await message.reply_text("[X] Sorry, I couldn't evaluate your answer.")
        # Show first answer on error
        await _send_first_answers(message, short_answers, full_answers)
        await _send_rule_if_enabled(message, session, rule_data)
        await _send_next_exercise_prompt(message, session)


async def pending_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pending command — show pending users for admin approval."""
    user = _require_user(update)

    if (
        settings.telegram.admin_user_id is None
        or user.id != settings.telegram.admin_user_id
    ):
        await _require_message(update).reply_text(
            "[X] You are not authorized to use this command."
        )
        return

    repository = DatabaseRepository()
    pending_users = repository.get_pending_users()

    if not pending_users:
        await _require_message(update).reply_text("No pending users at the moment.")
        return

    await _require_message(update).reply_text(
        f"📋 Pending users ({len(pending_users)}):",
        reply_markup=get_admin_pending_keyboard(pending_users),
    )


async def handle_admin_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle admin approve/reject actions."""
    query = _require_query(update)
    await query.answer()

    user = _require_user(update)

    if (
        settings.telegram.admin_user_id is None
        or user.id != settings.telegram.admin_user_id
    ):
        await _require_message(update).reply_text(
            "[X] You are not authorized to perform this action."
        )
        return

    _, action, target_id = (query.data or "").split(":")
    target_id = int(target_id)
    repository = DatabaseRepository()

    if action == "approve":
        repository.set_user_status(target_id, "approved", user.id)
        await _require_message(update).reply_text(
            f"✅ User {target_id} has been approved."
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    "✅ Your access has been approved! Use /start to begin practicing."
                ),
            )
        except Exception:
            logger.warning(f"Could not notify approved user {target_id}")
    elif action == "reject":
        repository.set_user_status(target_id, "rejected", user.id)
        await _require_message(update).reply_text(
            f"❌ User {target_id} has been rejected."
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ Your access has been denied.",
            )
        except Exception:
            logger.warning(f"Could not notify rejected user {target_id}")

    remaining = repository.get_pending_users()
    if remaining:
        await _require_message(update).reply_text(
            f"📋 Remaining pending ({len(remaining)}):",
            reply_markup=get_admin_pending_keyboard(remaining),
        )


start_handler = CommandHandler("start", start_command)
exercise_handler = CommandHandler("exercise", exercise_command)
rule_handler = CommandHandler("rule", rule_command)
pending_handler = CommandHandler("pending", pending_command)
topic_handler = CallbackQueryHandler(
    handle_topic_selection,
    pattern="^topic:",
)
exercise_action_handler = CallbackQueryHandler(
    handle_exercise_action,
    pattern="^action:",
)
admin_action_handler = CallbackQueryHandler(
    handle_admin_action,
    pattern="^admin:",
)
message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    handle_message,
)
