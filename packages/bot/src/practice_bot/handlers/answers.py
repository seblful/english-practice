"""Handling a text message: an answer to grade, or a question to explain."""

from practice_core.lesson import ActiveExercise
from practice_core.reveal import Reveal
from practice_runtime.errors import AgentError
from practice_runtime.logging import get_logger

from practice_bot import formatter, keyboards
from practice_bot.context import BotContext
from practice_bot.handlers.access import handler
from practice_bot.states import UserSession
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
    reveal: Reveal,
) -> None:
    """Show the book's answer, the rule behind it, and the next-exercise menu.

    What is in the reveal -- which answers, whether the book's whole sentence
    adds anything to the short form, whether there is a rule to quote -- was
    decided by :func:`practice_core.reveal.reveal_for`, shared with the app.
    This function renders it in Telegram's HTML and nothing more.

    Args:
        who: The user behind the update.
        session: The user's session.
        reveal: What to show for the question just answered.
    """
    if reveal.has_answer:
        await who.say(formatter.short_answers(reveal.answers))
        if reveal.show_full_answer:
            await who.say(formatter.full_answers(reveal.answers))

    if reveal.rule is not None:
        await who.say(
            formatter.rule_block(reveal.unit_reference, reveal.rule),
        )

    await who.say(
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
    The app cannot offer that -- a run there has a fixed length, so the
    question is spent -- which is why the two policies live in the front ends
    and only the reveal itself is shared.

    Args:
        who: The user behind the update.
        context: The handler context.
        session: The user's session.
        active: The exercise being answered.
    """
    try:
        evaluation = await context.agents.grader.evaluate(
            active.question,
            user_input=who.text,
            answers=active.answers,
            topic_name=active.topic_name,
            image=active.image,
        )
    except AgentError as exc:
        logger.warning(
            "grading_failed",
            user_id=who.user.id,
            question_id=active.question.id,
            error=str(exc),
        )
        # Revealed but with no verdict, which leaves it open for another attempt.
        active.give_up()
        await who.say(GRADING_FAILED)
        await _reveal(who, session, active.reveal(show_rule=session.show_rule))
        return

    active.record(evaluation)
    logger.info(
        "answer_graded",
        user_id=who.user.id,
        question_id=active.question.id,
        is_correct=evaluation.is_correct,
    )

    await who.say(formatter.evaluation(evaluation.is_correct))
    await _reveal(who, session, active.reveal(show_rule=session.show_rule))


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
            image=active.image,
            question_number=active.question.question_id,
            user_input=who.text,
            topic_name=active.topic_name,
        )
    except AgentError as exc:
        logger.warning("assist_failed", user_id=who.user.id, error=str(exc))
        await who.say(ASSIST_FAILED)
        return

    await who.say(formatter.assistant_answer(result.answer))


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
        await who.say(NO_EXERCISE_HINT)
        return

    if not who.text:
        await who.say(EMPTY_ANSWER_HINT)
        return

    if active.answered or active.grading:
        await _explain(who, context, active)
        return

    # Claimed before the first await: two messages at once would both be graded.
    with active.being_graded():
        await _grade(who, context, session, active)
