#!/usr/bin/env python3
"""Validate database integrity and consistency."""

import sqlite3
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


def get_db_path() -> Path:
    """Get database file path."""
    return get_project_root() / "data" / "development.db"


# How many offending rows to list before collapsing into a "... and N more" line.
MAX_LISTED_DEFAULT = 3
MAX_LISTED_IMAGES = 5
MAX_LISTED_QUESTIONS = 10


class DatabaseValidator:
    """Validator for database integrity and consistency."""

    def __init__(self, db_path: Path):
        """Open a connection to the database at ``db_path``."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.errors = []
        self.warnings = []

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def validate_image_blobs(self) -> dict:
        """Validate exercise image BLOBs in database."""
        results = {
            "status": "ok",
            "db_exercises": 0,
            "images_in_db": 0,
            "missing_images": [],
            "empty_images": [],
        }

        self.cursor.execute("SELECT COUNT(*) FROM exercises")
        results["db_exercises"] = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT COUNT(*) FROM exercise_images")
        results["images_in_db"] = self.cursor.fetchone()[0]

        # Exercises without image BLOBs
        self.cursor.execute(
            """
            SELECT e.exercise_id, u.unit_number, u.title
            FROM exercises e
            JOIN units u ON e.unit_id = u.id
            LEFT JOIN exercise_images ei ON e.id = ei.exercise_id
            WHERE ei.id IS NULL
            ORDER BY u.unit_number, e.exercise_number
            """
        )
        for row in self.cursor.fetchall():
            results["missing_images"].append(
                f"Unit {row['unit_number']}, Exercise {row['exercise_id']}"
            )

        # Image BLOBs with zero size
        self.cursor.execute(
            """
            SELECT e.exercise_id, u.unit_number, ei.id
            FROM exercise_images ei
            JOIN exercises e ON ei.exercise_id = e.id
            JOIN units u ON e.unit_id = u.id
            WHERE LENGTH(ei.image_data) = 0
            """
        )
        for row in self.cursor.fetchall():
            results["empty_images"].append(
                f"Unit {row['unit_number']}, Exercise {row['exercise_id']}"
            )

        if results["missing_images"] or results["empty_images"]:
            results["status"] = "error"

        # Show total image size
        total_bytes = self.cursor.execute(
            "SELECT COALESCE(SUM(LENGTH(image_data)), 0) FROM exercise_images"
        ).fetchone()[0]
        results["total_image_size_kb"] = total_bytes / 1024

        return results

    def validate_duplicates(self) -> dict:
        """Check for duplicate entries."""
        results = {
            "status": "ok",
            "duplicate_exercise_ids": [],
            "duplicate_question_ids": [],
            "duplicate_unit_numbers": [],
            "duplicate_topic_names": [],
        }

        # Duplicate exercise_ids
        self.cursor.execute(
            """
            SELECT exercise_id, COUNT(*) as cnt
            FROM exercises
            GROUP BY exercise_id
            HAVING cnt > 1
            """
        )
        for row in self.cursor.fetchall():
            results["duplicate_exercise_ids"].append(row["exercise_id"])

        # Duplicate question_ids within same exercise
        self.cursor.execute(
            """
            SELECT exercise_id, question_id, COUNT(*) as cnt
            FROM questions
            GROUP BY exercise_id, question_id
            HAVING cnt > 1
            """
        )
        for row in self.cursor.fetchall():
            self.cursor.execute(
                "SELECT exercise_id FROM exercises WHERE id = ?", (row["exercise_id"],)
            )
            ex_id = self.cursor.fetchone()["exercise_id"]
            results["duplicate_question_ids"].append(
                f"Exercise {ex_id}, Question {row['question_id']}"
            )

        # Duplicate unit_numbers
        self.cursor.execute(
            """
            SELECT unit_number, COUNT(*) as cnt
            FROM units
            GROUP BY unit_number
            HAVING cnt > 1
            """
        )
        for row in self.cursor.fetchall():
            results["duplicate_unit_numbers"].append(row["unit_number"])

        # Duplicate topic names
        self.cursor.execute(
            """
            SELECT name, COUNT(*) as cnt
            FROM topics
            GROUP BY name
            HAVING cnt > 1
            """
        )
        for row in self.cursor.fetchall():
            results["duplicate_topic_names"].append(row["name"])

        if any(
            results[k]
            for k in [
                "duplicate_exercise_ids",
                "duplicate_question_ids",
                "duplicate_unit_numbers",
                "duplicate_topic_names",
            ]
        ):
            results["status"] = "error"

        return results

    def validate_orphaned_data(self) -> dict:
        """Check for orphaned or missing data."""
        results = {
            "status": "ok",
            "exercises_without_questions": [],
            "questions_without_answers": [],
            "units_without_exercises": [],
            "topics_without_units": [],
        }

        # Exercises without questions
        self.cursor.execute(
            """
            SELECT e.exercise_id, u.unit_number, u.title
            FROM exercises e
            JOIN units u ON e.unit_id = u.id
            LEFT JOIN questions q ON e.id = q.exercise_id
            WHERE q.id IS NULL
            ORDER BY u.unit_number, e.exercise_number
            """
        )
        for row in self.cursor.fetchall():
            results["exercises_without_questions"].append(
                f"Unit {row['unit_number']}, Exercise {row['exercise_id']}"
            )

        # Questions without answers in question_answers table
        self.cursor.execute(
            """
            SELECT q.question_id, e.exercise_id
            FROM questions q
            JOIN exercises e ON q.exercise_id = e.id
            LEFT JOIN question_answers qa ON q.id = qa.question_id
            WHERE qa.id IS NULL AND q.is_open_ended = 0
            """
        )
        for row in self.cursor.fetchall():
            results["questions_without_answers"].append(
                f"Exercise {row['exercise_id']}, Question {row['question_id']}"
            )

        # Units without exercises
        self.cursor.execute(
            """
            SELECT u.unit_number, u.title
            FROM units u
            LEFT JOIN exercises e ON u.id = e.unit_id
            WHERE e.id IS NULL
            ORDER BY u.unit_number
            """
        )
        for row in self.cursor.fetchall():
            results["units_without_exercises"].append(
                f"Unit {row['unit_number']}: {row['title']}"
            )

        # Topics not linked to any units
        self.cursor.execute(
            """
            SELECT t.name
            FROM topics t
            LEFT JOIN unit_topics ut ON t.id = ut.topic_id
            WHERE ut.unit_id IS NULL
            ORDER BY t.name
            """
        )
        for row in self.cursor.fetchall():
            results["topics_without_units"].append(row["name"])

        if any(
            results[k]
            for k in [
                "exercises_without_questions",
                "questions_without_answers",
                "units_without_exercises",
                "topics_without_units",
            ]
        ):
            results["status"] = "error"

        return results

    def validate_referential_integrity(self) -> dict:
        """Check foreign key relationships."""
        results = {
            "status": "ok",
            "invalid_exercise_unit_ids": [],
            "invalid_question_exercise_ids": [],
            "invalid_unit_topic_unit_ids": [],
            "invalid_unit_topic_topic_ids": [],
            "invalid_topic_parents": [],
            "invalid_question_answers": [],
            "invalid_exercise_images": [],
        }

        # Exercises with invalid unit_id
        self.cursor.execute(
            """
            SELECT e.exercise_id, e.unit_id
            FROM exercises e
            LEFT JOIN units u ON e.unit_id = u.id
            WHERE u.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_exercise_unit_ids"].append(
                f"Exercise {row['exercise_id']} -> Unit ID {row['unit_id']}"
            )

        # Questions with invalid exercise_id
        self.cursor.execute(
            """
            SELECT q.id, q.exercise_id
            FROM questions q
            LEFT JOIN exercises e ON q.exercise_id = e.id
            WHERE e.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_question_exercise_ids"].append(
                f"Question {row['id']} -> Exercise ID {row['exercise_id']}"
            )

        # unit_topics with invalid unit_id
        self.cursor.execute(
            """
            SELECT ut.unit_id, ut.topic_id
            FROM unit_topics ut
            LEFT JOIN units u ON ut.unit_id = u.id
            WHERE u.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_unit_topic_unit_ids"].append(
                f"Unit ID {row['unit_id']} -> Topic ID {row['topic_id']}"
            )

        # unit_topics with invalid topic_id
        self.cursor.execute(
            """
            SELECT ut.unit_id, ut.topic_id
            FROM unit_topics ut
            LEFT JOIN topics t ON ut.topic_id = t.id
            WHERE t.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_unit_topic_topic_ids"].append(
                f"Unit ID {row['unit_id']} -> Topic ID {row['topic_id']}"
            )

        # Topics with invalid parent_topic_id
        self.cursor.execute(
            """
            SELECT t.id, t.name, t.parent_topic_id
            FROM topics t
            LEFT JOIN topics parent ON t.parent_topic_id = parent.id
            WHERE t.parent_topic_id IS NOT NULL AND parent.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_topic_parents"].append(
                f"Topic '{row['name']}' (ID {row['id']}) "
                f"-> Parent ID {row['parent_topic_id']}"
            )

        # question_answers with invalid question_id
        self.cursor.execute(
            """
            SELECT qa.id, qa.question_id
            FROM question_answers qa
            LEFT JOIN questions q ON qa.question_id = q.id
            WHERE q.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_question_answers"].append(
                f"Answer ID {row['id']} -> Question ID {row['question_id']}"
            )

        # exercise_images with invalid exercise_id
        self.cursor.execute(
            """
            SELECT ei.id, ei.exercise_id
            FROM exercise_images ei
            LEFT JOIN exercises e ON ei.exercise_id = e.id
            WHERE e.id IS NULL
            """
        )
        for row in self.cursor.fetchall():
            results["invalid_exercise_images"].append(
                f"Image ID {row['id']} -> Exercise ID {row['exercise_id']}"
            )

        if any(
            results[k]
            for k in [
                "invalid_exercise_unit_ids",
                "invalid_question_exercise_ids",
                "invalid_unit_topic_unit_ids",
                "invalid_unit_topic_topic_ids",
                "invalid_topic_parents",
                "invalid_question_answers",
                "invalid_exercise_images",
            ]
        ):
            results["status"] = "error"

        return results

    _REFERENTIAL_CHECKS = (
        ("invalid_exercise_unit_ids", "Invalid exercise unit_ids"),
        ("invalid_question_exercise_ids", "Invalid question exercise_ids"),
        ("invalid_unit_topic_unit_ids", "Invalid unit_topic unit_ids"),
        ("invalid_unit_topic_topic_ids", "Invalid unit_topic topic_ids"),
        ("invalid_topic_parents", "Invalid topic parents"),
        ("invalid_question_answers", "Invalid question_answers"),
        ("invalid_exercise_images", "Invalid exercise_images"),
    )

    @staticmethod
    def _print_issue(
        label: str,
        items: list,
        *,
        warn: bool = False,
        sample: int = 0,
        show_remainder: bool = False,
    ) -> int:
        """Print one issue line plus up to ``sample`` rows; return the row count.

        Args:
            label: Human-readable name of the issue.
            items: The offending rows; nothing is printed when empty.
            warn: Report as a warning rather than a failure.
            sample: How many offending rows to list underneath.
            show_remainder: Add a "... and N more" line when rows were elided.

        Returns:
            The number of offending rows.
        """
        if not items:
            return 0

        count = len(items)
        marker = "[[WARN]]" if warn else "[FAIL]"
        print(f"  {marker} {label}: {count}")
        for item in items[:sample]:
            print(f"    - {item}")
        if show_remainder and count > sample:
            print(f"    ... and {count - sample} more")
        return count

    def _report_image_blobs(self, img: dict) -> int:
        """Print the image BLOB section and return the error count."""
        print("\n[IMG] EXERCISE IMAGE BLOBS")
        if img["status"] == "ok":
            print(f"  [OK] Exercises in DB: {img['db_exercises']}")
            print(f"  [OK] Images in DB: {img['images_in_db']}")
            print(f"  [OK] Total image size: {img['total_image_size_kb']:.1f} KB")
            return 0

        print(f"  [FAIL] Exercises in DB: {img['db_exercises']}")
        print(f"  [FAIL] Images in DB: {img['images_in_db']}")

        errors = 0
        for key, title, remainder in (
            ("missing_images", "Missing Images", True),
            ("empty_images", "Empty Images", False),
        ):
            items = img.get(key)
            if not items:
                continue
            count = len(items)
            print(f"\n  {title} ({count}):")
            for item in items[:MAX_LISTED_IMAGES]:
                print(f"    - {item}")
            if remainder and count > MAX_LISTED_IMAGES:
                print(f"    ... and {count - MAX_LISTED_IMAGES} more")
            errors += count
        return errors

    def _report_duplicates(self, dup: dict) -> int:
        """Print the duplicate-detection section and return the error count."""
        print("\n[DUP] DUPLICATE DETECTION")
        if dup["status"] == "ok":
            print("  [OK] No duplicates found")
            return 0

        errors = self._print_issue(
            "Duplicate exercise_ids", dup["duplicate_exercise_ids"]
        )
        errors += self._print_issue(
            "Duplicate question_ids",
            dup["duplicate_question_ids"],
            sample=MAX_LISTED_DEFAULT,
        )
        errors += self._print_issue(
            "Duplicate unit_numbers", dup["duplicate_unit_numbers"]
        )
        errors += self._print_issue(
            "Duplicate topic names", dup["duplicate_topic_names"]
        )
        return errors

    def _report_orphaned(self, orphan: dict) -> tuple[int, int]:
        """Print the orphaned-data section and return (errors, warnings)."""
        print("\n[DATA] ORPHANED/MISSING DATA")
        if orphan["status"] == "ok":
            print("  [OK] No orphaned data found")
            return 0, 0

        errors = self._print_issue(
            "Exercises without questions",
            orphan["exercises_without_questions"],
            sample=MAX_LISTED_DEFAULT,
            show_remainder=True,
        )
        errors += self._print_issue(
            "Questions without answers",
            orphan["questions_without_answers"],
            sample=MAX_LISTED_QUESTIONS,
            show_remainder=True,
        )
        warnings = self._print_issue(
            "Units without exercises",
            orphan["units_without_exercises"],
            warn=True,
            sample=MAX_LISTED_DEFAULT,
        )
        warnings += self._print_issue(
            "Topics without units", orphan["topics_without_units"], warn=True
        )
        return errors, warnings

    def _report_referential(self, ref: dict) -> int:
        """Print the referential-integrity section and return the error count."""
        print("\n[REF] REFERENTIAL INTEGRITY")
        if ref["status"] == "ok":
            print("  [OK] All foreign keys valid")
            return 0

        return sum(
            self._print_issue(label, ref.get(key) or [])
            for key, label in self._REFERENTIAL_CHECKS
        )

    def print_report(self, results: dict) -> int:
        """Print validation report and return exit code."""
        print("\n" + "=" * 60)
        print("DATABASE VALIDATION REPORT")
        print("=" * 60)

        total_errors = self._report_image_blobs(results["image_blobs"])
        total_errors += self._report_duplicates(results["duplicates"])
        orphan_errors, total_warnings = self._report_orphaned(results["orphaned"])
        total_errors += orphan_errors
        total_errors += self._report_referential(results["referential"])

        print("\n" + "=" * 60)
        if total_errors == 0 and total_warnings == 0:
            print("[OK] ALL VALIDATIONS PASSED")
            exit_code = 0
        else:
            print(f"[ERR] ERRORS: {total_errors}, [WARN]  WARNINGS: {total_warnings}")
            exit_code = 1 if total_errors > 0 else 0
        print("=" * 60 + "\n")

        return exit_code


def main() -> int:
    """Main validation function."""
    db_path = get_db_path()

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print(f"Validating database: {db_path}")

    validator = DatabaseValidator(db_path)

    try:
        results = {
            "image_blobs": validator.validate_image_blobs(),
            "duplicates": validator.validate_duplicates(),
            "orphaned": validator.validate_orphaned_data(),
            "referential": validator.validate_referential_integrity(),
        }

        return validator.print_report(results)

    except Exception as e:
        print(f"Error during validation: {e}")
        return 1
    finally:
        validator.close()


if __name__ == "__main__":
    sys.exit(main())
