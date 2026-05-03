"""Bot keyboards for UI."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_user_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Create admin keyboard for a single pending user.

    Args:
        user_id: Telegram user ID.

    Returns:
        Inline keyboard markup.
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:approve:{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:reject:{user_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_pending_keyboard(pending_users: list[dict]) -> InlineKeyboardMarkup:
    """Create admin keyboard for pending user approvals.

    Args:
        pending_users: List of pending user dicts with telegram_id, full_name, telegram_username.

    Returns:
        Inline keyboard markup.
    """
    keyboard = []
    for user in pending_users:
        label = user["full_name"]
        if user["telegram_username"]:
            label += f" (@{user['telegram_username']})"
        keyboard.append([
            InlineKeyboardButton(f"✅ {label}", callback_data=f"admin:approve:{user['telegram_id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:reject:{user['telegram_id']}"),
        ])
    return InlineKeyboardMarkup(keyboard)


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
