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
from practice_core.schema import connect_content

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


class TestSchemaConstraints:
    """The check asks SQLite, rather than re-encoding the schema in Python."""

    def test_seeded_database_is_clean(self, validator: DatabaseValidator) -> None:
        assert validator.validate_constraints().passed is True

    def test_reports_a_question_pointing_at_no_exercise(
        self, validator: DatabaseValidator, seeded_db_path: Path
    ) -> None:
        """A bad row can still be written by a connection with the pragma off."""
        _execute(
            seeded_db_path,
            "INSERT INTO questions (id, exercise_id, question_id, display_order) "
            "VALUES (99, 404, '1', 1)",
        )

        result = validator.validate_constraints()

        assert result.issues[0].rows == ["questions rowid 99 -> exercises (fk 0)"]

    def test_reports_the_pragma_it_ran_under(
        self, validator: DatabaseValidator
    ) -> None:
        """The report says whether the rules were on, not just what it found."""
        assert validator.validate_constraints().facts == ["Foreign keys enforced: True"]

    def test_uniqueness_needs_no_check(self, seeded_db_path: Path) -> None:
        """SQLite refuses a duplicate outright, so none can be in the file.

        The old duplicate check needed a hand-built, constraint-free database
        to fire at all -- which is what showed it was a copy of the schema
        rather than a test of the data.
        """
        with (
            closing(connect_content(seeded_db_path)) as conn,
            pytest.raises(sqlite3.IntegrityError),
        ):
            conn.execute(
                "INSERT INTO units (unit_number, title) VALUES (1, 'Duplicate')"
            )


class TestRun:
    """Every registered check runs, in order."""

    def test_runs_every_check(self, validator: DatabaseValidator) -> None:
        results = validator.run()

        assert len(results) == len(CHECKS)
        assert [result.title.split()[0] for result in results] == [
            "[IMG]",
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
