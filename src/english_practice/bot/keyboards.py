"""Bot keyboards for UI."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_topic_keyboard(topics: list[dict]) -> InlineKeyboardMarkup:
    """Create topic selection keyboard.

    Args:
        topics: List of topic dicts with id and name.

    Returns:
        Inline keyboard markup.
    """
    keyboard = []

    for topic in topics:
        keyboard.append(
            [InlineKeyboardButton(topic["name"], callback_data=f"topic:{topic['id']}")]
        )

    return InlineKeyboardMarkup(keyboard)


def get_exercise_keyboard() -> InlineKeyboardMarkup:
    """Create exercise action keyboard.

    Returns:
        Inline keyboard markup.
    """
    keyboard = [
        [InlineKeyboardButton("📖 Show Unit", callback_data="action:show_unit")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_start_menu_keyboard(has_previous_topic: bool) -> InlineKeyboardMarkup:
    """Create start/menu keyboard with exercise options.

    Args:
        has_previous_topic: Whether user has a previous topic to continue.

    Returns:
        Inline keyboard markup.
    """
    keyboard = [
        [InlineKeyboardButton("🎲 Random", callback_data="topic:random")],
        [InlineKeyboardButton("📚 New Topic", callback_data="topic:new_topic")],
    ]
    if has_previous_topic:
        keyboard.append(
            [InlineKeyboardButton("🔄 Same Topic", callback_data="topic:same")]
        )
    return InlineKeyboardMarkup(keyboard)
