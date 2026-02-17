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

    keyboard.append(
        [
            InlineKeyboardButton(
                "🎲 Random from All Topics", callback_data="topic:random"
            )
        ]
    )

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
        [
            InlineKeyboardButton("📖 Show Unit", callback_data="action:show_unit"),
            InlineKeyboardButton(
                "🔄 New Exercise", callback_data="action:new_exercise"
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_new_exercise_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for new exercise options.

    Returns:
        Inline keyboard markup.
    """
    keyboard = [
        [
            InlineKeyboardButton("🎲 Random", callback_data="new:random"),
            InlineKeyboardButton("📚 Same Topic", callback_data="new:same"),
        ],
        [
            InlineKeyboardButton("🏠 Change Topic", callback_data="new:change"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
