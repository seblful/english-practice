-- Who may use the bot.
--
-- This table is the bot's alone. The app has one user, on their own phone,
-- with nobody to approve them, and the content pipeline has no users at all —
-- so the schema lives with the only code that reads or writes it, and the bot
-- creates it on startup rather than expecting the pipeline to have done it.
--
-- The content tables are in `practice_core/schema/content.sql`, shared with
-- everything that reads the book.

CREATE TABLE IF NOT EXISTS authorized_users (
    telegram_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    telegram_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at DATETIME,
    handled_by INTEGER
);
