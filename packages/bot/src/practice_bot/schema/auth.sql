-- Who may use the bot: the bot's own table, created by the bot on startup.

CREATE TABLE IF NOT EXISTS authorized_users (
    telegram_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    telegram_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at DATETIME,
    handled_by INTEGER
);
