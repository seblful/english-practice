"""Choosing a topic, drawing an exercise, and acting on the one in progress."""

import io

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
    """Draw an exercise and send it to the user."""
    # The draw only returns exercises with questions, so empty means empty topic.
    active = await context.content.draw(
        topic.id if topic else None,
        topic_name=topic.name if topic else None,
    )
    if active is None:
        logger.info("no_exercise_available", topic_id=topic.id if topic else None)
        await who.say(NO_EXERCISES_MESSAGE)
        return

    exercise = active.exercise
    context.start_exercise(who.user.id, active)
    logger.info(
        "exercise_sent",
        user_id=who.user.id,
        exercise_id=exercise.id,
        question_id=active.question.question_id,
        unit_number=exercise.unit.unit_number,
    )

    await who.say(formatter.topic_line(active.topic_name))
    await who.say(formatter.question_prompt(active.question.question_id))

    if active.image is None:
        logger.warning("exercise_image_missing", exercise_id=exercise.id)
        await who.say(NO_IMAGE_MESSAGE, reply_markup=keyboards.exercise_keyboard())
        return

    await who.message.reply_photo(
        photo=io.BytesIO(active.image), reply_markup=keyboards.exercise_keyboard()
    )


@handler()
async def topic_selection(who: Interaction, context: BotContext) -> None:
    """Act on a press in the topic menu."""
    choice = TOPICS.parse(who.callback_data)
    if choice is None:
        logger.warning("unparsable_topic_callback", data=who.callback_data)
        return

    match choice:
        case KeywordChoice(TopicSelection.NEW_TOPIC):
            topics = await context.content.list_topics()
            await who.say(
                CHOOSE_TOPIC_MESSAGE,
                reply_markup=keyboards.topics_keyboard(topics),
            )
        case KeywordChoice(TopicSelection.RANDOM):
            await send_exercise(who, context, topic=None)
        case KeywordChoice(TopicSelection.SAME):
            last_topic_id = context.sessions.get(who.user.id).last_topic_id
            topic = (
                await context.content.get_topic(last_topic_id)
                if last_topic_id is not None
                else None
            )
            await send_exercise(who, context, topic=topic)
        case SpecificTopic(topic_id):
            topic = await context.content.get_topic(topic_id)
            if topic is None:
                logger.warning("unknown_topic_selected", topic_id=topic_id)
                await who.say(NO_EXERCISES_MESSAGE)
                return
            await send_exercise(who, context, topic=topic)


@handler()
async def exercise_action(who: Interaction, context: BotContext) -> None:
    """Act on a button shown underneath an exercise."""
    action = ACTIONS.parse(who.callback_data)
    if action is None:
        logger.warning("unparsable_action_callback", data=who.callback_data)
        return

    active = context.sessions.get(who.user.id).active
    if active is None:
        await who.say(NO_ACTIVE_EXERCISE_MESSAGE)
        return

    match action:
        case ExerciseAction.SHOW_UNIT:
            unit = active.exercise.unit
            await who.say(
                formatter.unit_info(unit.unit_number, unit.title),
            )
