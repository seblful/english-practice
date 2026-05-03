#!/usr/bin/env python3
"""Initialize SQLite database and import existing data from JSON/markdown files."""

import json
import sqlite3
import sys
from pathlib import Path

from tqdm import tqdm


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


def get_db_path() -> Path:
    """Get database file path."""
    return get_project_root() / "data" / "content" / "english_practice.db"


def init_database(db_path: Path) -> None:
    """Create database and tables from schema."""
    schema_path = Path(__file__).parent / "schema.sql"

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print(f"Database initialized at: {db_path}")


def import_units(conn: sqlite3.Connection) -> None:
    """Import units from unit_to_title.json and grammar markdown files."""
    project_root = get_project_root()

    # Load unit titles
    with open(
        project_root / "data" / "content" / "metadata" / "unit_to_title.json",
        "r",
        encoding="utf-8",
    ) as f:
        units_data = json.load(f)

    # Check which grammar files exist
    grammar_dir = project_root / "data" / "content" / "grammar"
    existing_grammar = {int(f.stem) for f in grammar_dir.glob("*.md")}

    cursor = conn.cursor()
    for unit in tqdm(units_data, desc="Importing units"):
        unit_num = unit["unit_id"]
        if unit_num in existing_grammar:
            cursor.execute(
                """
                INSERT OR IGNORE INTO units (unit_number, title, grammar_md_path)
                VALUES (?, ?, ?)
                """,
                (unit_num, unit["title"], f"grammar/{unit_num}.md"),
            )

    conn.commit()
    print(
        f"Imported {cursor.execute('SELECT COUNT(*) FROM units').fetchone()[0]} units"
    )


def parse_exercise_id(exercise_id: str) -> tuple[int, int]:
    """Parse exercise_id like '1.1' into (page, exercise_number)."""
    parts = exercise_id.split(".")
    return int(parts[0]), int(parts[1])


def import_exercises_and_questions(conn: sqlite3.Connection) -> None:
    """Import exercises and questions from answers_full.json and rules.json."""
    project_root = get_project_root()

    answers_full_path = (
        project_root / "data" / "content" / "metadata" / "answers_full.json"
    )
    rules_path = project_root / "data" / "content" / "metadata" / "rules.json"

    if not answers_full_path.exists():
        raise FileNotFoundError(
            f"answers_full.json not found at {answers_full_path}. Run extraction first."
        )

    if not rules_path.exists():
        raise FileNotFoundError(
            f"rules.json not found at {rules_path}. Run extraction first."
        )

    with open(answers_full_path, "r", encoding="utf-8") as f:
        answers_data = json.load(f)

    with open(rules_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)

    rules_map: dict[str, dict] = {}
    for unit in rules_data.get("units", []):
        for exercise in unit.get("exercises", []):
            exercise_id = exercise["exercise_id"]
            for q in exercise.get("questions", []):
                rules_map[f"{exercise_id}:{q['question_id']}"] = q

    cursor = conn.cursor()
    exercises_imported = 0
    questions_imported = 0
    answers_imported = 0

    for unit in tqdm(answers_data.get("units", []), desc="Importing exercises"):
        unit_id_db = cursor.execute(
            "SELECT id FROM units WHERE unit_number = ?", (int(unit["unit_id"]),)
        ).fetchone()

        if not unit_id_db:
            continue

        unit_id_db = unit_id_db[0]

        for exercise in unit.get("exercises", []):
            exercise_id = exercise["exercise_id"]
            page_num, ex_num = parse_exercise_id(exercise_id)

            cursor.execute(
                """
                INSERT OR IGNORE INTO exercises
                (exercise_id, unit_id, exercise_number)
                VALUES (?, ?, ?)
                """,
                (exercise_id, unit_id_db, ex_num),
            )

            exercise_db_id = cursor.lastrowid
            if not exercise_db_id:
                exercise_db_id = cursor.execute(
                    "SELECT id FROM exercises WHERE exercise_id = ?", (exercise_id,)
                ).fetchone()[0]
            else:
                exercises_imported += 1

            # Store image blob if file exists
            image_path = f"exercises/{page_num}/{exercise_id}.png"
            image_full_path = project_root / "data" / "content" / image_path
            if image_full_path.exists():
                image_data = image_full_path.read_bytes()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO exercise_images
                    (exercise_id, image_data)
                    VALUES (?, ?)
                    """,
                    (exercise_db_id, image_data),
                )

            for idx, question in enumerate(exercise.get("questions", [])):
                question_id = question["question_id"]
                is_open_ended = question.get("is_open_ended", False)

                rule_info = rules_map.get(f"{exercise_id}:{question_id}", {})
                section_letter = rule_info.get("section_letter")
                rule = rule_info.get("rule")

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO questions
                    (exercise_id, question_id, is_open_ended, section_letter, rule, display_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        exercise_db_id,
                        question_id,
                        int(is_open_ended),
                        section_letter,
                        rule,
                        idx,
                    ),
                )

                question_db_id = cursor.lastrowid
                if not question_db_id:
                    question_db_id = cursor.execute(
                        "SELECT id FROM questions WHERE exercise_id = ? AND question_id = ?",
                        (exercise_db_id, question_id),
                    ).fetchone()[0]
                else:
                    questions_imported += 1

                if not is_open_ended:
                    for answer in question.get("answers", []):
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO question_answers
                            (question_id, short_answer, full_answer)
                            VALUES (?, ?, ?)
                            """,
                            (
                                question_db_id,
                                answer["short_answer"],
                                answer["full_answer"],
                            ),
                        )
                        if cursor.lastrowid:
                            answers_imported += 1

    conn.commit()
    print(
        f"Imported {exercises_imported} exercises, {questions_imported} questions, {answers_imported} answers"
    )


def import_topics(conn: sqlite3.Connection) -> None:
    """Import topics from topic_to_unit.json."""
    project_root = get_project_root()

    with open(
        project_root / "data" / "content" / "metadata" / "topic_to_unit.json",
        "r",
        encoding="utf-8",
    ) as f:
        topics_data = json.load(f)

    cursor = conn.cursor()

    for topic_item in tqdm(topics_data, desc="Importing topics"):
        topic_name = topic_item["topic"]
        unit_ids = topic_item["unit_ids"]

        cursor.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", (topic_name,))

        topic_id = cursor.execute(
            "SELECT id FROM topics WHERE name = ?", (topic_name,)
        ).fetchone()[0]

        # Link to units
        for unit_num in unit_ids:
            cursor.execute(
                """
                INSERT OR IGNORE INTO unit_topics (unit_id, topic_id)
                SELECT id, ? FROM units WHERE unit_number = ?
                """,
                (topic_id, unit_num),
            )

    conn.commit()
    print(
        f"Imported {cursor.execute('SELECT COUNT(*) FROM topics').fetchone()[0]} topics"
    )


def main() -> int:
    """Main function to set up database and import data."""
    db_path = get_db_path()

    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing database if it exists
    if db_path.exists():
        print(f"Removing existing database: {db_path}")
        db_path.unlink()

    # Initialize database
    init_database(db_path)

    # Connect and import data
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        import_units(conn)
        import_exercises_and_questions(conn)
        import_topics(conn)

        # Show summary
        cursor = conn.cursor()
        print("\n" + "=" * 50)
        print("DATABASE IMPORT SUMMARY")
        print("=" * 50)

        tables = ["units", "exercises", "exercise_images", "questions", "question_answers", "topics"]
        for table in tables:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table:20s}: {count:5d} rows")

        # Show image storage size
        total_bytes = cursor.execute(
            "SELECT COALESCE(SUM(LENGTH(image_data)), 0) FROM exercise_images"
        ).fetchone()[0]
        print(f"{'images size':20s}: {total_bytes / 1024:.1f} KB")

        print("=" * 50)

    except Exception as e:
        print(f"Error importing data: {e}")
        return 1
    finally:
        conn.close()

    print(f"\nDatabase ready at: {db_path}")
    print(f"File size: {db_path.stat().st_size / 1024:.1f} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
