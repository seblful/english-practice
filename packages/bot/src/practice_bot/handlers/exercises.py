"""Choosing a topic, drawing an exercise, and acting on the one in progress."""

import io

from practice_core.lesson import topic_label
from practice_core.models import Topic
from practice_runtime.logging import get_logger

from practice_bot import formatter, keyboards
from practice_bot.callbacks import (
    ACTIONS,
    TOPICS,
    ExerciseAction,
    KeywordChoice,
    SpecificTopic,
    TopicSelection,
)
from practice_bot.context import BotContext
from practice_bot.handlers.access import handler
from practice_bot.states import ActiveExercise
from practice_bot.updates import Interaction

logger = get_logger(__name__)

NO_EXERCISES_MESSAGE = "🔍 No exercises found for this topic. Please try another."
NO_IMAGE_MESSAGE = "⚠️ This exercise has no image in the database."
NO_ACTIVE_EXERCISE_MESSAGE = "🔍 No active exercise. Use /start to pick a topic."
CHOOSE_TOPIC_MESSAGE = "Select a topic:"


async def send_exercise(
    who: Interaction,
    context: BotContext,
    topic: Topic | None,
) -> None:
    """Draw an exercise and send it to the user.

    Args:
        who: The user behind the update.
        context: The handler context.
        topic: The topic to draw from, or ``None`` to draw from all of them.
    """
    # The draw only returns exercises that have questions, so an empty result
    # means the topic itself is empty.
    drawn = await context.repository.draw_question(topic.id if topic else None)
    if drawn is None:
        logger.info("no_exercise_available", topic_id=topic.id if topic else None)
        await who.message.reply_text(NO_EXERCISES_MESSAGE)
        return

    exercise, question, image = drawn
    topic_name = topic_label(
        topic_name=topic.name if topic else None, unit=exercise.unit
    )

    context.start_exercise(
        who.user.id,
        ActiveExercise(
            exercise=exercise,
            question=question,
            topic_id=topic.id if topic else None,
            topic_name=topic_name,
            image=image,
        ),
    )
    logger.info(
        "exercise_sent",
        user_id=who.user.id,
        exercise_id=exercise.id,
        question_id=question.question_id,
        unit_number=exercise.unit.unit_number,
    )

    await who.message.reply_text(formatter.topic_line(topic_name), parse_mode="HTML")
    await who.message.reply_text(
        formatter.question_prompt(question.question_id), parse_mode="HTML"
    )

    if image is None:
        logger.warning("exercise_image_missing", exercise_id=exercise.id)
        await who.message.reply_text(
            NO_IMAGE_MESSAGE, reply_markup=keyboards.exercise_keyboard()
        )
        return

    await who.message.reply_photo(
        photo=io.BytesIO(image), reply_markup=keyboards.exercise_keyboard()
    )


@handler()
async def topic_selection(who: Interaction, context: BotContext) -> None:
    """Act on a press in the topic menu.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    choice = TOPICS.parse(who.callback_data)
    if choice is None:
        logger.warning("unparsable_topic_callback", data=who.callback_data)
        return

    match choice:
        case KeywordChoice(TopicSelection.NEW_TOPIC):
            topics = await context.repository.list_topics()
            await who.message.reply_text(
                CHOOSE_TOPIC_MESSAGE,
                reply_markup=keyboards.topics_keyboard(topics),
            )
        case KeywordChoice(TopicSelection.RANDOM):
            await send_exercise(who, context, topic=None)
        case KeywordChoice(TopicSelection.SAME):
            last_topic_id = context.sessions.get(who.user.id).last_topic_id
            topic = (
                await context.repository.get_topic(last_topic_id)
                if last_topic_id is not None
                else None
            )
            await send_exercise(who, context, topic=topic)
        case SpecificTopic(topic_id):
            topic = await context.repository.get_topic(topic_id)
            if topic is None:
                logger.warning("unknown_topic_selected", topic_id=topic_id)
                await who.message.reply_text(NO_EXERCISES_MESSAGE)
                return
            await send_exercise(who, context, topic=topic)


@handler()
async def exercise_action(who: Interaction, context: BotContext) -> None:
    """Act on a button shown underneath an exercise.

    Args:
        who: The user behind the update.
        context: The handler context.
    """
    action = ACTIONS.parse(who.callback_data)
    if action is None:
        logger.warning("unparsable_action_callback", data=who.callback_data)
        return

    active = context.sessions.get(who.user.id).active
    if active is None:
        await who.message.reply_text(NO_ACTIVE_EXERCISE_MESSAGE)
        return

    match action:
        case ExerciseAction.SHOW_UNIT:
            unit = active.exercise.unit
            await who.message.reply_text(
                formatter.unit_info(unit.unit_number, unit.title),
                parse_mode="HTML",
            )
