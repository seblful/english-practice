"""Validate database integrity and consistency.

A check answers one question about the database and returns a
:class:`CheckResult`. Whether it passed is derived from the rows it collected,
so adding a check means writing it and listing it in :data:`CHECKS` — there is
no separate place to register its printing, and none to declare its verdict.
"""

import sqlite3
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from practice_core.schema import connect_content

from practice_extraction.settings import get_settings

# How many offending rows to list before collapsing into a "... and N more" line.
MAX_LISTED_DEFAULT = 3
MAX_LISTED_IMAGES = 5
MAX_LISTED_QUESTIONS = 10


def _unit_and_exercise(row: sqlite3.Row) -> str:
    """Describe an offending row by the exercise it belongs to."""
    return f"Unit {row['unit_number']}, Exercise {row['exercise_id']}"


@dataclass(frozen=True, slots=True)
class Issue:
    """One kind of problem, and the offending rows a check found for it.

    ``warning`` separates "the database is wrong" from "the database is thin":
    warnings are reported but do not fail the run.
    """

    label: str
    rows: list[str]
    warning: bool = False
    sample: int = 0
    show_remainder: bool = False


@dataclass(frozen=True, slots=True)
class CheckResult:
    """What one check found.

    ``facts`` are counts worth printing either way; ``issues`` are what can
    fail. The verdict is derived from the issues, so a check cannot pass by
    forgetting to say it failed.
    """

    title: str
    all_clear: str
    issues: list[Issue] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        """How many offending rows fail the run."""
        return sum(len(issue.rows) for issue in self.issues if not issue.warning)

    @property
    def warnings(self) -> int:
        """How many offending rows are reported but tolerated."""
        return sum(len(issue.rows) for issue in self.issues if issue.warning)

    @property
    def passed(self) -> bool:
        """Whether the check found nothing at all."""
        return not self.errors and not self.warnings


class DatabaseValidator:
    """Runs the integrity checks against one database file.

    Use it as a context manager; it owns a connection for its lifetime.
    """

    def __init__(self, db_path: Path):
        """Open a connection to the database at ``db_path``."""
        self.db_path = db_path
        # Opened the way the pipeline writes it, so that
        # `PRAGMA foreign_key_check` reports against the same rules the
        # inserts were made under.
        self.conn = connect_content(db_path)
        self.cursor = self.conn.cursor()

    def __enter__(self) -> "DatabaseValidator":
        """Return the validator itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection, however the block ended."""
        self.conn.close()

    def _count(self, sql: str) -> int:
        """Return the single number a counting query yields."""
        return self.cursor.execute(sql).fetchone()[0]

    def _labels(self, sql: str, describe: Callable[[sqlite3.Row], str]) -> list[str]:
        """Run a query and describe each offending row it returns.

        Args:
            sql: A query selecting the rows that should not exist.
            describe: Renders one row as a line for the report.

        Returns:
            One description per offending row; empty when the check is clean.
        """
        return [describe(row) for row in self.cursor.execute(sql).fetchall()]

    def validate_image_blobs(self) -> CheckResult:
        """Check that every exercise has a non-empty image blob."""
        total_bytes = self._count(
            "SELECT COALESCE(SUM(LENGTH(image_data)), 0) FROM exercise_images"
        )
        return CheckResult(
            title="[IMG] EXERCISE IMAGE BLOBS",
            all_clear="Every exercise has an image",
            facts=[
                f"Exercises in DB: {self._count('SELECT COUNT(*) FROM exercises')}",
                f"Images in DB: {self._count('SELECT COUNT(*) FROM exercise_images')}",
                f"Total image size: {total_bytes / 1024:.1f} KB",
            ],
            issues=[
                Issue(
                    "Missing Images",
                    self._labels(
                        """
                        SELECT e.exercise_id, u.unit_number
                        FROM exercises e
                        JOIN units u ON e.unit_id = u.id
                        LEFT JOIN exercise_images ei ON e.id = ei.exercise_id
                        WHERE ei.id IS NULL
                        ORDER BY u.unit_number, e.exercise_number
                        """,
                        _unit_and_exercise,
                    ),
                    sample=MAX_LISTED_IMAGES,
                    show_remainder=True,
                ),
                Issue(
                    "Empty Images",
                    self._labels(
                        """
                        SELECT e.exercise_id, u.unit_number
                        FROM exercise_images ei
                        JOIN exercises e ON ei.exercise_id = e.id
                        JOIN units u ON e.unit_id = u.id
                        WHERE LENGTH(ei.image_data) = 0
                        """,
                        _unit_and_exercise,
                    ),
                    sample=MAX_LISTED_IMAGES,
                ),
            ],
        )

    def validate_orphaned_data(self) -> CheckResult:
        """Check for rows nothing points at, and rows that point at nothing."""
        return CheckResult(
            title="[DATA] ORPHANED/MISSING DATA",
            all_clear="No orphaned data found",
            issues=[
                Issue(
                    "Exercises without questions",
                    self._labels(
                        """
                        SELECT e.exercise_id, u.unit_number
                        FROM exercises e
                        JOIN units u ON e.unit_id = u.id
                        LEFT JOIN questions q ON e.id = q.exercise_id
                        WHERE q.id IS NULL
                        ORDER BY u.unit_number, e.exercise_number
                        """,
                        _unit_and_exercise,
                    ),
                    sample=MAX_LISTED_DEFAULT,
                    show_remainder=True,
                ),
                Issue(
                    "Questions without answers",
                    self._labels(
                        """
                        SELECT q.question_id, e.exercise_id
                        FROM questions q
                        JOIN exercises e ON q.exercise_id = e.id
                        LEFT JOIN question_answers qa ON q.id = qa.question_id
                        WHERE qa.id IS NULL AND q.is_open_ended = 0
                        """,
                        lambda r: (
                            f"Exercise {r['exercise_id']}, Question {r['question_id']}"
                        ),
                    ),
                    sample=MAX_LISTED_QUESTIONS,
                    show_remainder=True,
                ),
                Issue(
                    "Units without exercises",
                    self._labels(
                        """
                        SELECT u.unit_number, u.title
                        FROM units u
                        LEFT JOIN exercises e ON u.id = e.unit_id
                        WHERE e.id IS NULL
                        ORDER BY u.unit_number
                        """,
                        lambda r: f"Unit {r['unit_number']}: {r['title']}",
                    ),
                    warning=True,
                    sample=MAX_LISTED_DEFAULT,
                ),
                Issue(
                    "Topics without units",
                    self._labels(
                        """
                        SELECT t.name
                        FROM topics t
                        LEFT JOIN unit_topics ut ON t.id = ut.topic_id
                        WHERE ut.unit_id IS NULL
                        ORDER BY t.name
                        """,
                        lambda r: str(r["name"]),
                    ),
                    warning=True,
                ),
            ],
        )

    def validate_constraints(self) -> CheckResult:
        """Ask SQLite whether the schema's own constraints hold.

        This used to be two checks, ninety-odd lines, re-encoding seven
        foreign keys as ``LEFT JOIN ... IS NULL`` queries and four ``UNIQUE``
        constraints as ``GROUP BY ... HAVING COUNT(*) > 1``. That was a second
        copy of `content.sql` written in Python, and it drifted: add a table to
        the schema and nothing here noticed.

        ``PRAGMA foreign_key_check`` runs the real thing against the real
        schema. Uniqueness needs no check at all: SQLite enforces it on every
        insert, whether or not foreign keys are on, so a duplicate cannot be
        in a database built from this schema -- which the old check proved by
        needing a constraint-free database to fire at all.

        Returns:
            One issue per row that points at something missing.
        """
        return CheckResult(
            title="[REF] SCHEMA CONSTRAINTS",
            all_clear="Every foreign key resolves",
            facts=[f"Foreign keys enforced: {self._foreign_keys_on()}"],
            issues=[
                Issue(
                    "Rows pointing at something that is not there",
                    [
                        f"{row['table']} rowid {row['rowid']} "
                        f"-> {row['parent']} (fk {row['fkid']})"
                        for row in self.cursor.execute(
                            "PRAGMA foreign_key_check"
                        ).fetchall()
                    ],
                    sample=MAX_LISTED_DEFAULT,
                    show_remainder=True,
                ),
            ],
        )

    def _foreign_keys_on(self) -> bool:
        """Return whether this connection is enforcing foreign keys."""
        return bool(self._count("PRAGMA foreign_keys"))

    def run(self) -> list[CheckResult]:
        """Run every registered check, in order."""
        return [check(self) for check in CHECKS]


# Every check the report runs. Adding one here is the whole registration.
CHECKS: tuple[Callable[[DatabaseValidator], CheckResult], ...] = (
    DatabaseValidator.validate_image_blobs,
    DatabaseValidator.validate_orphaned_data,
    DatabaseValidator.validate_constraints,
)


def _print_issue(issue: Issue) -> None:
    """Print one issue line plus up to ``sample`` of its rows."""
    count = len(issue.rows)
    if not count:
        return

    marker = "[WARN]" if issue.warning else "[FAIL]"
    print(f"  {marker} {issue.label}: {count}")
    for row in issue.rows[: issue.sample]:
        print(f"    - {row}")
    if issue.show_remainder and count > issue.sample:
        print(f"    ... and {count - issue.sample} more")


def print_report(results: Sequence[CheckResult]) -> int:
    """Print the report and return the process exit code.

    Args:
        results: What every check found, in the order they ran.

    Returns:
        1 when any check collected an error, 0 otherwise. Warnings are printed
        but do not fail the run.
    """
    print("\n" + "=" * 60)
    print("DATABASE VALIDATION REPORT")
    print("=" * 60)

    for result in results:
        print(f"\n{result.title}")
        marker = "[OK]" if result.passed else "[FAIL]"
        for fact in result.facts:
            print(f"  {marker} {fact}")
        if result.passed:
            if not result.facts:
                print(f"  [OK] {result.all_clear}")
            continue
        for issue in result.issues:
            _print_issue(issue)

    total_errors = sum(result.errors for result in results)
    total_warnings = sum(result.warnings for result in results)

    print("\n" + "=" * 60)
    if not total_errors and not total_warnings:
        print("[OK] ALL VALIDATIONS PASSED")
    else:
        print(f"[ERR] ERRORS: {total_errors}, [WARN]  WARNINGS: {total_warnings}")
    print("=" * 60 + "\n")

    return 1 if total_errors else 0


def main(db_path: Path | None = None) -> int:
    """Validate the database the application reads.

    Args:
        db_path: The database to check. The configured one when omitted, so
            that what this checks is what the bot opens.

    Returns:
        The process exit code.
    """
    db_path = db_path or get_settings().paths.database_path

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print(f"Validating database: {db_path}")

    try:
        with DatabaseValidator(db_path) as validator:
            return print_report(validator.run())
    except Exception:
        print("Error during validation:")
        traceback.print_exc()
        return 1
