"""Handling a text message: an answer to grade, or a question to explain."""

from collections.abc import Sequence

from practice_core.grading import answers_to_show
from practice_core.models import QuestionAnswer
from practice_runtime.errors import AgentError
from practice_runtime.logging import get_logger

from practice_bot import formatter, keyboards
from practice_bot.context import BotContext
from practice_bot.handlers.access import handler
from practice_bot.states import ActiveExercise, UserSession
from practice_bot.updates import Interaction

logger = get_logger(__name__)

NO_EXERCISE_HINT = "👋 Use /start to begin practicing English grammar."
EMPTY_ANSWER_HINT = "✍️ Send me your answer as text."
GRADING_FAILED = "⚠️ I couldn't grade that right now — here's the book's answer."
ASSIST_FAILED = "⚠️ Sorry, I couldn't answer that right now. Try asking again."
NEXT_EXERCISE_PROMPT = "Choose next exercise:"


async def _reveal(
    who: Interaction,
    session: UserSession,
    active: ActiveExercise,
    answers: Sequence[QuestionAnswer],
) -> None:
    """Show the book's answer, the rule behind it, and the next-exercise menu.

    Args:
        who: The user behind the update.
        session: The user's session.
        active: The exercise being answered.
        answers: The answers to reveal; may be empty for an open-ended question.
    """
    if answers:
        await who.message.reply_text(
            formatter.short_answers(answers), parse_mode="HTML"
        )
        await who.message.reply_text(formatter.full_answers(answers), parse_mode="HTML")

    question = active.question
    if session.show_rule and question.rule:
        await who.message.reply_text(
            formatter.rule_block(
                active.exercise.unit.unit_number,
                question.section_letter,
                question.rule,
            ),
            parse_mode="HTML",
        )

    await who.message.reply_text(
        NEXT_EXERCISE_PROMPT,
        reply_markup=keyboards.main_menu_keyboard(session.has_previous_topic),
    )


async def _grade(
    who: Interaction,
    context: BotContext,
    session: UserSession,
    active: ActiveExercise,
) -> None:
    """Grade the user's answer and reveal the book's.

    A failed grading deliberately leaves the question unanswered, so the next
    message is treated as another attempt rather than as a follow-up question.

    Args:
        who: The user behind the update.
        context: The handler context.
        session: The user's session.
        active: The exercise being answered.
    """
    answers = await context.repository.list_answers(active.question.id)

    try:
        evaluation = await context.agents.evaluate_answer(
            image_data=active.image,
            question_number=active.question.question_id,
            user_input=who.text,
            answers=answers,
            is_open_ended=active.question.is_open_ended,
            topic_name=active.topic_name,
            rule=active.question.rule,
        )
    except AgentError as exc:
        logger.warning(
            "grading_failed",
            user_id=who.user.id,
            question_id=active.question.id,
            error=str(exc),
        )
        await who.message.reply_text(GRADING_FAILED)
        await _reveal(who, session, active, answers[:1])
        return

    active.answered = True
    logger.info(
        "answer_graded",
        user_id=who.user.id,
        question_id=active.question.id,
        is_correct=evaluation.is_correct,
    )

    await who.message.reply_text(
        formatter.evaluation(evaluation.is_correct), parse_mode="HTML"
    )
    await _reveal(who, session, active, answers_to_show(answers, evaluation.answer_idx))


async def _explain(
    who: Interaction, context: BotContext, active: ActiveExercise
) -> None:
    """Answer a follow-up question about the exercise just answered.

    Args:
        who: The user behind the update.
        context: The handler context.
        active: The exercise being discussed.
    """
    try:
        result = await context.agents.assist(
            user_id=who.user.id,
            exercise_id=active.exercise.id,
            image_data=active.image,
            question_number=active.question.question_id,
            user_input=who.text,
            topic_name=active.topic_name,
        )
    except AgentError as exc:
        logger.warning("assist_failed", user_id=who.user.id, error=str(exc))
        await who.message.reply_text(ASSIST_FAILED)
        return

    await who.message.reply_text(
        formatter.assistant_answer(result.answer), parse_mode="HTML"
    )


@handler()
async def text_message(who: Interaction, context: BotContext) -> None:
    """Route a text message to grading or to the assistant.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    session = context.sessions.get(who.user.id)
    active = session.active

    if active is None:
        await who.message.reply_text(NO_EXERCISE_HINT)
        return

    if not who.text:
        await who.message.reply_text(EMPTY_ANSWER_HINT)
        return

    if active.answered:
        await _explain(who, context, active)
        return

    await _grade(who, context, session, active)
