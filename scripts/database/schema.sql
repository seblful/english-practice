-- English Practice App Database Schema
-- Simplified: Core content only (no user/AI tracking)

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================
-- CORE CONTENT TABLES (Static Data)
-- ============================================

-- Grammar units from your markdown files
CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY,
    unit_number INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    grammar_md_path TEXT NOT NULL  -- e.g., "grammar/1.md"
);

-- Individual exercises (images stored as BLOB)
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY,
    exercise_id TEXT NOT NULL UNIQUE,  -- e.g., "1.1", "2.3"
    unit_id INTEGER NOT NULL,
    exercise_number INTEGER NOT NULL,
    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
);

-- Exercise image data stored as BLOB
CREATE TABLE IF NOT EXISTS exercise_images (
    id INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL UNIQUE,
    image_data BLOB NOT NULL,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
);

-- Questions within exercises (from answers.json)
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,  -- e.g., "2", "2a", "10 a", "2–5" (can contain letters/ranges)
    is_open_ended BOOLEAN DEFAULT 0,
    section_letter TEXT,
    rule TEXT,
    display_order INTEGER DEFAULT 0,  -- For sorting in UI
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
    UNIQUE(exercise_id, question_id)
);

-- Question answers (multiple answers per question with full answer)
CREATE TABLE IF NOT EXISTS question_answers (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL,
    short_answer TEXT NOT NULL,
    full_answer TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    UNIQUE(question_id, short_answer)
);

-- Topics/tags for categorization
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_topic_id INTEGER,
    FOREIGN KEY (parent_topic_id) REFERENCES topics(id)
);

-- Link units to topics (many-to-many)
CREATE TABLE IF NOT EXISTS unit_topics (
    unit_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    PRIMARY KEY (unit_id, topic_id),
    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

-- ============================================
-- AUTHORIZATION
-- ============================================

CREATE TABLE IF NOT EXISTS authorized_users (
    telegram_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    telegram_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at DATETIME,
    handled_by INTEGER
);

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

CREATE INDEX IF NOT EXISTS idx_exercises_unit ON exercises(unit_id);
CREATE INDEX IF NOT EXISTS idx_exercise_images_exercise ON exercise_images(exercise_id);
CREATE INDEX IF NOT EXISTS idx_questions_exercise ON questions(exercise_id);
CREATE INDEX IF NOT EXISTS idx_question_answers_question ON question_answers(question_id);
