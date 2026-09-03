"""Build the content database from what the extraction stages wrote.

The last stage of the pipeline, and the only one that writes SQLite. Every
directory it reads comes from the one
:class:`~practice_runtime.settings.PathSettings` the rest of the project uses,
and the tables, with their constraints enforced, come from
:func:`practice_core.schema.connect_content` — so
the file this builds is by construction the file the bot opens and the bundler
re-encodes.
"""

import json
import sqlite3
import traceback
from pathlib import Path

from practice_core.schema import connect_content
from practice_runtime.settings import PathSettings
from tqdm import tqdm

from practice_extraction.settings import get_settings
from practice_extraction.stages import (
    ANSWERS_FULL_FILENAME,
    RULES_FILENAME,
    TOPIC_MAP_FILENAME,
    UNIT_TITLES_FILENAME,
)

# The four names below used to be fresh literals here, two of them already
# declared by the stages that write the files.

_SUMMARY_TABLES = (
    "units",
    "exercises",
    "exercise_images",
    "questions",
    "question_answers",
    "topics",
)


def init_database(db_path: Path) -> None:
    """Create the database and the content tables.

    Args:
        db_path: Where to create the file.
    """
    connect_content(db_path, create=True).close()
    print(f"Database initialized at: {db_path}")


def import_units(conn: sqlite3.Connection, paths: PathSettings) -> None:
    """Import units from unit_to_title.json and grammar markdown files.

    Args:
        conn: An open connection to the database being built.
        paths: Where the extracted content lives.
    """
    unit_titles_path = paths.metadata_dir / UNIT_TITLES_FILENAME
    with unit_titles_path.open(encoding="utf-8") as f:
        units_data = json.load(f)

    # A unit with no grammar page never made it through the pipeline, so it
    # would arrive with no rules and nothing to explain.
    existing_grammar = {int(f.stem) for f in paths.grammar_md_dir.glob("*.md")}

    cursor = conn.cursor()
    for unit in tqdm(units_data, desc="Importing units"):
        unit_num = unit["unit_id"]
        if unit_num in existing_grammar:
            cursor.execute(
                """
                INSERT OR IGNORE INTO units (unit_number, title)
                VALUES (?, ?)
                """,
                (unit_num, unit["title"]),
            )

    conn.commit()
    total_units = cursor.execute("SELECT COUNT(*) FROM units").fetchone()[0]
    print(f"Units in database: {total_units}")


def parse_exercise_id(exercise_id: str) -> tuple[int, int]:
    """Parse exercise_id like '1.1' into (unit_number, exercise_number)."""
    parts = exercise_id.split(".")
    return int(parts[0]), int(parts[1])


def _load_import_metadata(paths: PathSettings) -> tuple[dict, dict]:
    """Load answers_full.json and rules.json, failing if extraction has not run.

    Args:
        paths: Where the extracted content lives.

    Returns:
        The answers and the rules, as the stages wrote them.

    Raises:
        FileNotFoundError: If either file is missing.
    """
    answers_full_path = paths.metadata_dir / ANSWERS_FULL_FILENAME
    rules_path = paths.metadata_dir / RULES_FILENAME

    if not answers_full_path.exists():
        raise FileNotFoundError(
            f"{ANSWERS_FULL_FILENAME} not found at {answers_full_path}. "
            "Run extraction first."
        )

    if not rules_path.exists():
        raise FileNotFoundError(
            f"{RULES_FILENAME} not found at {rules_path}. Run extraction first."
        )

    with answers_full_path.open(encoding="utf-8") as f:
        answers_data = json.load(f)

    with rules_path.open(encoding="utf-8") as f:
        rules_data = json.load(f)

    return answers_data, rules_data


def _build_rules_map(rules_data: dict) -> dict[str, dict]:
    """Index rule metadata by "<exercise_id>:<question_id>"."""
    rules_map: dict[str, dict] = {}
    for unit in rules_data.get("units", []):
        for exercise in unit.get("exercises", []):
            exercise_id = exercise["exercise_id"]
            for q in exercise.get("questions", []):
                rules_map[f"{exercise_id}:{q['question_id']}"] = q
    return rules_map


def _store_exercise_image(
    cursor: sqlite3.Cursor,
    paths: PathSettings,
    exercise_db_id: int,
    unit_number: int,
    exercise_id: str,
) -> None:
    """Store the exercise image blob when the image file exists."""
    image_full_path = paths.exercises_dir / str(unit_number) / f"{exercise_id}.png"
    if not image_full_path.exists():
        return

    cursor.execute(
        """
        INSERT OR IGNORE INTO exercise_images
        (exercise_id, image_data)
        VALUES (?, ?)
        """,
        (exercise_db_id, image_full_path.read_bytes()),
    )


def _import_answers(cursor: sqlite3.Cursor, question_db_id: int, question: dict) -> int:
    """Insert a question's answers and return how many were newly added."""
    added = 0
    for answer in question.get("answers", []):
        cursor.execute(
            """
            INSERT OR IGNORE INTO question_answers
            (question_id, short_answer, full_answer)
            VALUES (?, ?, ?)
            """,
            (question_db_id, answer["short_answer"], answer["full_answer"]),
        )
        # An ignored INSERT leaves lastrowid pointing at the previous insert,
        # so rowcount is the only reliable "did this row land" signal.
        if cursor.rowcount == 1:
            added += 1
    return added


def _import_questions(
    cursor: sqlite3.Cursor,
    exercise_db_id: int,
    exercise: dict,
    exercise_id: str,
    rules_map: dict[str, dict],
) -> tuple[int, int]:
    """Import one exercise's questions, returning (questions, answers) added."""
    questions_imported = 0
    answers_imported = 0

    for idx, question in enumerate(exercise.get("questions", [])):
        question_id = question["question_id"]
        is_open_ended = question.get("is_open_ended", False)
        rule_info = rules_map.get(f"{exercise_id}:{question_id}", {})

        cursor.execute(
            """
            INSERT OR IGNORE INTO questions
            (exercise_id, question_id, is_open_ended,
             section_letter, rule, display_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                exercise_db_id,
                question_id,
                int(is_open_ended),
                rule_info.get("section_letter"),
                rule_info.get("rule"),
                idx,
            ),
        )

        if cursor.rowcount == 1:
            questions_imported += 1
        question_db_id = cursor.execute(
            "SELECT id FROM questions WHERE exercise_id = ? AND question_id = ?",
            (exercise_db_id, question_id),
        ).fetchone()[0]

        if not is_open_ended:
            answers_imported += _import_answers(cursor, question_db_id, question)

    return questions_imported, answers_imported


def import_exercises_and_questions(
    conn: sqlite3.Connection, paths: PathSettings
) -> None:
    """Import exercises and questions from answers_full.json and rules.json.

    Args:
        conn: An open connection to the database being built.
        paths: Where the extracted content lives.
    """
    answers_data, rules_data = _load_import_metadata(paths)
    rules_map = _build_rules_map(rules_data)

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
            unit_number, ex_num = parse_exercise_id(exercise_id)

            cursor.execute(
                """
                INSERT OR IGNORE INTO exercises
                (exercise_id, unit_id, exercise_number)
                VALUES (?, ?, ?)
                """,
                (exercise_id, unit_id_db, ex_num),
            )

            if cursor.rowcount == 1:
                exercises_imported += 1
            exercise_db_id = cursor.execute(
                "SELECT id FROM exercises WHERE exercise_id = ?", (exercise_id,)
            ).fetchone()[0]

            _store_exercise_image(
                cursor, paths, exercise_db_id, unit_number, exercise_id
            )
            q_added, a_added = _import_questions(
                cursor, exercise_db_id, exercise, exercise_id, rules_map
            )
            questions_imported += q_added
            answers_imported += a_added

    conn.commit()
    print(
        f"Imported {exercises_imported} exercises, "
        f"{questions_imported} questions, {answers_imported} answers"
    )


def import_topics(conn: sqlite3.Connection, paths: PathSettings) -> None:
    """Import topics from topic_to_unit.json.

    Args:
        conn: An open connection to the database being built.
        paths: Where the extracted content lives.
    """
    topics_path = paths.metadata_dir / TOPIC_MAP_FILENAME
    with topics_path.open(encoding="utf-8") as f:
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
    total_topics = cursor.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    print(f"Topics in database: {total_topics}")


def main(*, force: bool = False, paths: PathSettings | None = None) -> int:
    """Build the content database from the extracted JSON and images.

    Args:
        force: Delete an existing database first. Without it an existing file
            is left alone: this rebuilds from scratch, so running it by
            accident against a populated database would destroy it.
        paths: Where the extracted content lives, and where the database goes.
            The configured layout when omitted.

    Returns:
        The process exit code.
    """
    paths = paths or get_settings().paths
    db_path = paths.database_path

    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        if not force:
            print(f"Database already exists at {db_path}.")
            print("Pass --force to delete it and rebuild from scratch.")
            return 1
        print(f"Removing existing database: {db_path}")
        db_path.unlink()

    # Initialize database
    init_database(db_path)

    # Every insert below goes through a connection that enforces the schema's
    # own foreign keys, so a row pointing at nothing fails here rather than
    # being found afterwards by a separate program re-checking the same rules.
    conn = connect_content(db_path)

    try:
        import_units(conn, paths)
        import_exercises_and_questions(conn, paths)
        import_topics(conn, paths)

        # Show summary
        cursor = conn.cursor()
        print("\n" + "=" * 50)
        print("DATABASE IMPORT SUMMARY")
        print("=" * 50)

        for table in _SUMMARY_TABLES:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table:20s}: {count:5d} rows")

        # Show image storage size
        total_bytes = cursor.execute(
            "SELECT COALESCE(SUM(LENGTH(image_data)), 0) FROM exercise_images"
        ).fetchone()[0]
        print(f"{'images size':20s}: {total_bytes / 1024:.1f} KB")

        print("=" * 50)

    except Exception:
        print("Error importing data:")
        traceback.print_exc()
        return 1
    finally:
        conn.close()

    print(f"\nDatabase ready at: {db_path}")
    print(f"File size: {db_path.stat().st_size / 1024:.1f} KB")

    return 0
