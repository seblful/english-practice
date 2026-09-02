"""Tests for the database population script.

The script reads a content tree and writes a SQLite file, so these tests build
a miniature tree in ``tmp_path`` and assert on the database that comes out.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from practice_runtime.settings import PathSettings

from practice_extraction.populate import (
    _build_rules_map,
    main,
    parse_exercise_id,
)


@pytest.fixture
def content_root(paths: PathSettings) -> PathSettings:
    """Fill the configured layout with a one-unit content tree.

    The layout comes from ``PathSettings``, the same group ``populate`` reads,
    so a directory renamed there moves this tree with it.
    """
    metadata = paths.metadata_dir
    (paths.exercises_dir / "1").mkdir(parents=True, exist_ok=True)

    (paths.grammar_md_dir / "1.md").write_text("# Present Continuous")
    (paths.exercises_dir / "1" / "1.1.png").write_bytes(b"\x89PNG")

    (metadata / "unit_to_title.json").write_text(
        json.dumps([{"unit_id": 1, "title": "Present Continuous"}])
    )
    (metadata / "topic_to_unit.json").write_text(
        json.dumps([{"topic": "Present Tenses", "unit_ids": [1]}])
    )
    (metadata / "answers_full.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "1",
                        "exercises": [
                            {
                                "exercise_id": "1.1",
                                "questions": [
                                    {
                                        "question_id": "1",
                                        "is_open_ended": False,
                                        "answers": [
                                            {
                                                "short_answer": "is doing",
                                                "full_answer": "He is doing.",
                                            },
                                            {
                                                "short_answer": "'s doing",
                                                "full_answer": "He's doing.",
                                            },
                                        ],
                                    },
                                    {"question_id": "2", "is_open_ended": True},
                                ],
                            }
                        ],
                    }
                ]
            }
        )
    )
    (metadata / "rules.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "exercises": [
                            {
                                "exercise_id": "1.1",
                                "questions": [
                                    {
                                        "question_id": "1",
                                        "section_letter": "A",
                                        "rule": "Use the present continuous.",
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        )
    )
    return paths


@pytest.fixture
def db_path(content_root: PathSettings) -> Path:
    """Where the filled-in layout says the database goes."""
    return content_root.database_path


def _rows(db_path: Path, sql: str) -> list[tuple]:
    """Return every row a query yields."""
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(sql).fetchall()


class TestParseExerciseId:
    """Tests for splitting an exercise id."""

    def test_splits_into_unit_and_exercise_number(self) -> None:
        assert parse_exercise_id("12.3") == (12, 3)


class TestBuildRulesMap:
    """Tests for indexing the extracted rules."""

    def test_keys_by_exercise_and_question(self) -> None:
        data = {
            "units": [
                {
                    "exercises": [
                        {
                            "exercise_id": "1.1",
                            "questions": [{"question_id": "2", "rule": "r"}],
                        }
                    ]
                }
            ]
        }

        assert _build_rules_map(data) == {"1.1:2": {"question_id": "2", "rule": "r"}}

    def test_empty_input(self) -> None:
        assert _build_rules_map({}) == {}


class TestMain:
    """Tests for building the database end to end."""

    def test_builds_the_configured_database(
        self,
        content_root: PathSettings,
        db_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert main(paths=content_root) == 0

        assert db_path.exists()
        assert _rows(db_path, "SELECT unit_number, title FROM units") == [
            (1, "Present Continuous")
        ]
        assert _rows(db_path, "SELECT exercise_id FROM exercises") == [("1.1",)]
        assert "Database ready at" in capsys.readouterr().out

    def test_imports_questions_with_their_rules(
        self, content_root: PathSettings, db_path: Path
    ) -> None:
        main(paths=content_root)

        assert _rows(
            db_path,
            "SELECT question_id, is_open_ended, section_letter, rule "
            "FROM questions ORDER BY display_order",
        ) == [
            ("1", 0, "A", "Use the present continuous."),
            ("2", 1, None, None),
        ]

    def test_imports_every_accepted_answer(
        self, content_root: PathSettings, db_path: Path
    ) -> None:
        main(paths=content_root)

        assert _rows(
            db_path, "SELECT short_answer, full_answer FROM question_answers"
        ) == [
            ("is doing", "He is doing."),
            ("'s doing", "He's doing."),
        ]

    def test_stores_the_exercise_image_as_a_blob(
        self, content_root: PathSettings, db_path: Path
    ) -> None:
        main(paths=content_root)

        assert _rows(db_path, "SELECT image_data FROM exercise_images") == [
            (b"\x89PNG",)
        ]

    def test_links_units_to_their_topic(
        self, content_root: PathSettings, db_path: Path
    ) -> None:
        main(paths=content_root)

        assert _rows(
            db_path,
            "SELECT t.name, u.unit_number FROM unit_topics ut "
            "JOIN topics t ON t.id = ut.topic_id "
            "JOIN units u ON u.id = ut.unit_id",
        ) == [("Present Tenses", 1)]

    def test_refuses_to_overwrite_an_existing_database(
        self,
        content_root: PathSettings,
        db_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """This rebuilds from scratch, so an accidental run would be fatal."""
        db_path.write_bytes(b"precious")

        assert main(paths=content_root) == 1
        assert "Pass --force" in capsys.readouterr().out
        assert db_path.read_bytes() == b"precious"

    def test_force_rebuilds_from_scratch(
        self, content_root: PathSettings, db_path: Path
    ) -> None:
        db_path.write_bytes(b"stale")

        assert main(force=True, paths=content_root) == 0
        assert _rows(db_path, "SELECT exercise_id FROM exercises") == [("1.1",)]

    def test_a_broken_content_tree_is_reported_not_raised(
        self,
        db_path: Path,
        content_root: PathSettings,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (content_root.metadata_dir / "rules.json").unlink()

        assert main(paths=content_root) == 1
        assert "Error importing data" in capsys.readouterr().out

    def test_reads_the_configured_database_path_when_given_none(
        self, content_root: PathSettings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CLI passes the layout; a direct call falls back to the settings."""
        monkeypatch.setattr(
            "practice_extraction.populate.get_settings",
            lambda: SimpleNamespace(paths=content_root),
        )

        assert main() == 0
        assert content_root.database_path.exists()
