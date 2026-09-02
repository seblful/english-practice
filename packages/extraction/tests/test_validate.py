"""Tests for the database validation script.

These run against a real SQLite file built from the real ``schema.sql``, so a
renamed column breaks the checks rather than silently skipping them.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pytest

from practice_extraction.validate import (
    CHECKS,
    CheckResult,
    DatabaseValidator,
    Issue,
    main,
    print_report,
)


@pytest.fixture
def validator(seeded_db_path: Path) -> Iterator[DatabaseValidator]:
    """A validator over the seeded database."""
    with DatabaseValidator(seeded_db_path) as validator:
        yield validator


def _execute(db_path: Path, sql: str, params: tuple = ()) -> None:
    """Run one statement against the database and commit it."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(sql, params)


class TestCheckResult:
    """The verdict is derived from the rows, never declared."""

    def test_no_rows_passes(self) -> None:
        result = CheckResult(title="T", all_clear="fine", issues=[Issue("none", [])])

        assert result.passed is True
        assert (result.errors, result.warnings) == (0, 0)

    def test_rows_fail_the_run(self) -> None:
        result = CheckResult(title="T", all_clear="fine", issues=[Issue("bad", ["a"])])

        assert result.passed is False
        assert result.errors == 1

    def test_warnings_are_reported_but_do_not_fail(self) -> None:
        result = CheckResult(
            title="T",
            all_clear="fine",
            issues=[Issue("thin", ["a", "b"], warning=True)],
        )

        assert result.passed is False
        assert (result.errors, result.warnings) == (0, 2)
        assert print_report([result]) == 0

    def test_counts_do_not_make_a_check_fail(self) -> None:
        """Facts are printed either way; only issues decide the verdict."""
        result = CheckResult(title="T", all_clear="fine", facts=["Exercises: 433"])

        assert result.passed is True


class TestImageBlobs:
    """Tests for the exercise-image check."""

    def test_counts_are_reported_as_facts(self, validator: DatabaseValidator) -> None:
        result = validator.validate_image_blobs()

        assert result.facts[0] == "Exercises in DB: 3"
        assert result.facts[1] == "Images in DB: 1"

    def test_reports_exercises_with_no_image(
        self, validator: DatabaseValidator
    ) -> None:
        """Only exercise 1.1 is seeded with a blob."""
        result = validator.validate_image_blobs()

        assert result.issues[0].rows == ["Unit 1, Exercise 1.2", "Unit 2, Exercise 2.1"]
        assert result.errors == 2

    def test_reports_an_empty_blob(
        self, validator: DatabaseValidator, seeded_db_path: Path
    ) -> None:
        """A broken import stores a zero-length blob rather than no row."""
        _execute(
            seeded_db_path,
            "UPDATE exercise_images SET image_data = ? WHERE exercise_id = 1",
            (b"",),
        )

        result = validator.validate_image_blobs()

        assert result.issues[1].rows == ["Unit 1, Exercise 1.1"]


class TestDuplicates:
    """Tests for the duplicate check.

    The current ``schema.sql`` makes every duplicate this check looks for
    unreachable: ``units.unit_number``, ``exercises.exercise_id``,
    ``topics.name`` and ``questions(exercise_id, question_id)`` are all UNIQUE.
    The check earns its keep only against a database built by an older schema,
    which is what the legacy fixture below stands in for.
    """

    def test_seeded_database_is_clean(self, validator: DatabaseValidator) -> None:
        assert validator.validate_duplicates().passed is True

    def test_reports_duplicates_in_a_database_without_the_constraints(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "legacy.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE units (id INTEGER PRIMARY KEY, unit_number INTEGER,
                                    title TEXT);
                CREATE TABLE exercises (id INTEGER PRIMARY KEY, exercise_id TEXT,
                                        unit_id INTEGER, exercise_number INTEGER);
                CREATE TABLE questions (id INTEGER PRIMARY KEY, exercise_id INTEGER,
                                        question_id TEXT);
                CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT);

                INSERT INTO units VALUES (1, 1, 'A'), (2, 1, 'B');
                INSERT INTO exercises VALUES (1, '1.1', 1, 1), (2, '1.1', 1, 2);
                INSERT INTO questions VALUES (1, 1, '3'), (2, 1, '3');
                INSERT INTO topics VALUES (1, 'Tenses'), (2, 'Tenses');
                """
            )

        with DatabaseValidator(path) as validator:
            result = validator.validate_duplicates()

        assert [issue.rows for issue in result.issues] == [
            ["1.1"],
            ["Exercise 1.1, Question 3"],
            ["1"],
            ["Tenses"],
        ]


class TestOrphanedData:
    """Tests for the orphaned-data check."""

    def test_seeded_database_has_known_gaps(self, validator: DatabaseValidator) -> None:
        """Exercise 1.2 has no questions, and one topic has no units."""
        result = validator.validate_orphaned_data()

        assert result.issues[0].rows == ["Unit 1, Exercise 1.2"]
        assert result.issues[3].rows == ["Unused Topic"]
        assert result.warnings == 1

    def test_open_ended_questions_need_no_answers(
        self, validator: DatabaseValidator
    ) -> None:
        """Question 1 of exercise 1.1 is open-ended, so it is not reported."""
        result = validator.validate_orphaned_data()

        assert result.issues[1].rows == ["Exercise 2.1, Question 1"]

    def test_every_unit_has_exercises(self, validator: DatabaseValidator) -> None:
        assert validator.validate_orphaned_data().issues[2].rows == []


class TestReferentialIntegrity:
    """Tests for the foreign-key check."""

    def test_seeded_database_is_clean(self, validator: DatabaseValidator) -> None:
        assert validator.validate_referential_integrity().passed is True

    def test_reports_a_question_pointing_at_no_exercise(
        self, validator: DatabaseValidator, seeded_db_path: Path
    ) -> None:
        """Foreign keys are per-connection, so a bad row can be written."""
        _execute(
            seeded_db_path,
            "INSERT INTO questions (id, exercise_id, question_id, display_order) "
            "VALUES (99, 404, '1', 1)",
        )

        result = validator.validate_referential_integrity()

        assert result.issues[1].rows == ["Question 99 -> Exercise ID 404"]


class TestRun:
    """Every registered check runs, in order."""

    def test_runs_every_check(self, validator: DatabaseValidator) -> None:
        results = validator.run()

        assert len(results) == len(CHECKS)
        assert [result.title.split()[0] for result in results] == [
            "[IMG]",
            "[DUP]",
            "[DATA]",
            "[REF]",
        ]


class TestPrintReport:
    """Tests for the printed report and the exit code."""

    def test_clean_database_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = print_report(
            [CheckResult(title="[X] CHECK", all_clear="Nothing wrong")]
        )

        assert exit_code == 0
        assert "ALL VALIDATIONS PASSED" in capsys.readouterr().out

    def test_errors_set_the_exit_code(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = print_report(
            [
                CheckResult(
                    title="[X] CHECK",
                    all_clear="Nothing wrong",
                    issues=[Issue("Broken", ["a", "b"])],
                )
            ]
        )

        out = capsys.readouterr().out
        assert exit_code == 1
        assert "[FAIL] Broken: 2" in out
        assert "ERRORS: 2" in out

    def test_lists_a_sample_and_elides_the_rest(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        print_report(
            [
                CheckResult(
                    title="[X] CHECK",
                    all_clear="Nothing wrong",
                    issues=[
                        Issue(
                            "Broken",
                            ["a", "b", "c", "d"],
                            sample=2,
                            show_remainder=True,
                        )
                    ],
                )
            ]
        )

        out = capsys.readouterr().out
        assert "    - a" in out
        assert "    - c" not in out
        assert "... and 2 more" in out

    def test_facts_are_printed_when_the_check_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        print_report(
            [CheckResult(title="[X] CHECK", all_clear="fine", facts=["Rows: 7"])]
        )

        assert "[OK] Rows: 7" in capsys.readouterr().out

    def test_seeded_database_reports_its_known_gaps(
        self, validator: DatabaseValidator, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = print_report(validator.run())

        out = capsys.readouterr().out
        assert exit_code == 1
        assert "[FAIL] Exercises without questions: 1" in out
        assert "[WARN] Topics without units: 1" in out


class TestMain:
    """Tests for the script entry point."""

    def test_validates_the_configured_database(
        self,
        seeded_db_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        settings = Mock()
        settings.paths.database_path = seeded_db_path
        monkeypatch.setattr(
            "practice_extraction.validate.get_settings", lambda: settings
        )

        exit_code = main()

        assert exit_code == 1  # the seed data has a questionless exercise
        assert str(seeded_db_path) in capsys.readouterr().out

    def test_missing_database_is_reported(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        settings = Mock()
        settings.paths.database_path = tmp_path / "nowhere.db"
        monkeypatch.setattr(
            "practice_extraction.validate.get_settings", lambda: settings
        )

        assert main() == 1
        assert "Database not found" in capsys.readouterr().out

    def test_a_broken_database_is_reported_not_raised(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An operator gets a traceback and an exit code, not a stack unwind."""
        empty = tmp_path / "empty.db"
        empty.write_bytes(b"")
        settings = Mock()
        settings.paths.database_path = empty
        monkeypatch.setattr(
            "practice_extraction.validate.get_settings", lambda: settings
        )

        assert main() == 1
        assert "Error during validation" in capsys.readouterr().out
