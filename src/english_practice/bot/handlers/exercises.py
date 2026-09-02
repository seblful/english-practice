"""Choosing a topic, drawing an exercise, and acting on the one in progress."""

import io
import random

from english_practice.bot import formatter, keyboards
from english_practice.bot.callbacks import (
    ExerciseAction,
    KeywordChoice,
    SpecificTopic,
    TopicSelection,
    parse_topic_choice,
)
from english_practice.bot.context import BotContext
from english_practice.bot.handlers.access import handler
from english_practice.bot.states import ActiveExercise
from english_practice.bot.updates import Interaction
from english_practice.logging import get_logger
from english_practice.models.book import Topic

logger = get_logger(__name__)

NO_EXERCISES_MESSAGE = "🔍 No exercises found for this topic. Please try another."
NO_IMAGE_MESSAGE = "⚠️ This exercise has no image in the database."
NO_ACTIVE_EXERCISE_MESSAGE = "🔍 No active exercise. Use /start to pick a topic."
CHOOSE_TOPIC_MESSAGE = "Select a topic:"
RANDOM_TOPIC_LABEL = "Random"


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
    exercise = await context.repository.random_exercise(topic.id if topic else None)

    # The draw only returns exercises that have questions, so an empty result
    # means the topic itself is empty.
    if exercise is None or not exercise.questions:
        logger.info("no_exercise_available", topic_id=topic.id if topic else None)
        await who.message.reply_text(NO_EXERCISES_MESSAGE)
        return

    question = random.choice(exercise.questions)
    topic_name = topic.name if topic else exercise.unit.topic_name or RANDOM_TOPIC_LABEL
    image = await context.repository.get_exercise_image(exercise.id)

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
    choice = parse_topic_choice(who.callback_data)
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
    action = ExerciseAction.parse(who.callback_data)
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
