#!/usr/bin/env python3
"""Validate database integrity and consistency."""

import sys
from pathlib import Path
import sqlite3


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


def get_db_path() -> Path:
    """Get database file path."""
    return get_project_root() / "data" / "content" / "english_practice.db"


class DatabaseValidator:
    """Validator for database integrity and consistency."""

    def __init__(self, db_path: Path):
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
                f"Topic '{row['name']}' (ID {row['id']}) -> Parent ID {row['parent_topic_id']}"
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

    def validate_cross_references(self) -> dict:
        """Validate cross-references with external files."""
        results = {
            "status": "ok",
            "missing_grammar_files": [],
        }

        # Check grammar markdown files exist
        self.cursor.execute("SELECT unit_number, grammar_md_path FROM units")
        for row in self.cursor.fetchall():
            md_path = get_project_root() / "data" / "content" / row["grammar_md_path"]
            if not md_path.exists():
                results["missing_grammar_files"].append(
                    f"Unit {row['unit_number']}: {row['grammar_md_path']}"
                )

        if results["missing_grammar_files"]:
            results["status"] = "error"

        return results

    def print_report(self, results: dict) -> int:
        """Print validation report and return exit code."""
        print("\n" + "=" * 60)
        print("DATABASE VALIDATION REPORT")
        print("=" * 60)

        total_errors = 0
        total_warnings = 0

        # Image BLOBs
        print("\n[IMG] EXERCISE IMAGE BLOBS")
        img = results["image_blobs"]
        if img["status"] == "ok":
            print(f"  [OK] Exercises in DB: {img['db_exercises']}")
            print(f"  [OK] Images in DB: {img['images_in_db']}")
            print(f"  [OK] Total image size: {img['total_image_size_kb']:.1f} KB")
        else:
            print(f"  [FAIL] Exercises in DB: {img['db_exercises']}")
            print(f"  [FAIL] Images in DB: {img['images_in_db']}")
            if img["missing_images"]:
                print(f"\n  Missing Images ({len(img['missing_images'])}):")
                for item in img["missing_images"][:5]:
                    print(f"    - {item}")
                if len(img["missing_images"]) > 5:
                    print(f"    ... and {len(img['missing_images']) - 5} more")
                total_errors += len(img["missing_images"])
            if img["empty_images"]:
                print(f"\n  Empty Images ({len(img['empty_images'])}):")
                for item in img["empty_images"][:5]:
                    print(f"    - {item}")
                total_errors += len(img["empty_images"])

        # Duplicates
        print("\n[DUP] DUPLICATE DETECTION")
        dup = results["duplicates"]
        if dup["status"] == "ok":
            print("  [OK] No duplicates found")
        else:
            if dup["duplicate_exercise_ids"]:
                print(
                    f"  [FAIL] Duplicate exercise_ids: {len(dup['duplicate_exercise_ids'])}"
                )
                total_errors += len(dup["duplicate_exercise_ids"])
            if dup["duplicate_question_ids"]:
                print(
                    f"  [FAIL] Duplicate question_ids: {len(dup['duplicate_question_ids'])}"
                )
                for item in dup["duplicate_question_ids"][:3]:
                    print(f"    - {item}")
                total_errors += len(dup["duplicate_question_ids"])
            if dup["duplicate_unit_numbers"]:
                print(
                    f"  [FAIL] Duplicate unit_numbers: {len(dup['duplicate_unit_numbers'])}"
                )
                total_errors += len(dup["duplicate_unit_numbers"])
            if dup["duplicate_topic_names"]:
                print(
                    f"  [FAIL] Duplicate topic names: {len(dup['duplicate_topic_names'])}"
                )
                total_errors += len(dup["duplicate_topic_names"])

        # Orphaned Data
        print("\n[DATA] ORPHANED/MISSING DATA")
        orphan = results["orphaned"]
        if orphan["status"] == "ok":
            print("  [OK] No orphaned data found")
        else:
            if orphan["exercises_without_questions"]:
                print(
                    f"  [FAIL] Exercises without questions: {len(orphan['exercises_without_questions'])}"
                )
                for item in orphan["exercises_without_questions"][:3]:
                    print(f"    - {item}")
                if len(orphan["exercises_without_questions"]) > 3:
                    print(
                        f"    ... and {len(orphan['exercises_without_questions']) - 3} more"
                    )
                total_errors += len(orphan["exercises_without_questions"])
            if orphan["questions_without_answers"]:
                print(
                    f"  [FAIL] Questions without answers: {len(orphan['questions_without_answers'])}"
                )
                for item in orphan["questions_without_answers"][:10]:
                    print(f"    - {item}")
                if len(orphan["questions_without_answers"]) > 10:
                    print(
                        f"    ... and {len(orphan['questions_without_answers']) - 10} more"
                    )
                total_errors += len(orphan["questions_without_answers"])
            if orphan["units_without_exercises"]:
                print(
                    f"  [[WARN]] Units without exercises: {len(orphan['units_without_exercises'])}"
                )
                for item in orphan["units_without_exercises"][:3]:
                    print(f"    - {item}")
                total_warnings += len(orphan["units_without_exercises"])
            if orphan["topics_without_units"]:
                print(
                    f"  [[WARN]] Topics without units: {len(orphan['topics_without_units'])}"
                )
                total_warnings += len(orphan["topics_without_units"])

        # Referential Integrity
        print("\n[REF] REFERENTIAL INTEGRITY")
        ref = results["referential"]
        if ref["status"] == "ok":
            print("  [OK] All foreign keys valid")
        else:
            if ref["invalid_exercise_unit_ids"]:
                print(
                    f"  [FAIL] Invalid exercise unit_ids: {len(ref['invalid_exercise_unit_ids'])}"
                )
                total_errors += len(ref["invalid_exercise_unit_ids"])
            if ref["invalid_question_exercise_ids"]:
                print(
                    f"  [FAIL] Invalid question exercise_ids: {len(ref['invalid_question_exercise_ids'])}"
                )
                total_errors += len(ref["invalid_question_exercise_ids"])
            if ref["invalid_unit_topic_unit_ids"]:
                print(
                    f"  [FAIL] Invalid unit_topic unit_ids: {len(ref['invalid_unit_topic_unit_ids'])}"
                )
                total_errors += len(ref["invalid_unit_topic_unit_ids"])
            if ref["invalid_unit_topic_topic_ids"]:
                print(
                    f"  [FAIL] Invalid unit_topic topic_ids: {len(ref['invalid_unit_topic_topic_ids'])}"
                )
                total_errors += len(ref["invalid_unit_topic_topic_ids"])
            if ref["invalid_topic_parents"]:
                print(
                    f"  [FAIL] Invalid topic parents: {len(ref['invalid_topic_parents'])}"
                )
                total_errors += len(ref["invalid_topic_parents"])
            if ref.get("invalid_question_answers"):
                print(
                    f"  [FAIL] Invalid question_answers: {len(ref['invalid_question_answers'])}"
                )
                total_errors += len(ref["invalid_question_answers"])
            if ref.get("invalid_exercise_images"):
                print(
                    f"  [FAIL] Invalid exercise_images: {len(ref['invalid_exercise_images'])}"
                )
                total_errors += len(ref["invalid_exercise_images"])

        # Cross References
        print("\n[CROSS] CROSS-REFERENCE VALIDATION")
        cross = results["cross_references"]
        if cross["status"] == "ok":
            print("  [OK] All external references valid")
        else:
            if cross["missing_grammar_files"]:
                print(
                    f"  [[WARN]] Missing grammar files: {len(cross['missing_grammar_files'])}"
                )
                for item in cross["missing_grammar_files"][:3]:
                    print(f"    - {item}")
                total_warnings += len(cross["missing_grammar_files"])

        # Summary
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
            "cross_references": validator.validate_cross_references(),
        }

        exit_code = validator.print_report(results)
        return exit_code

    except Exception as e:
        print(f"Error during validation: {e}")
        return 1
    finally:
        validator.close()


if __name__ == "__main__":
    sys.exit(main())
