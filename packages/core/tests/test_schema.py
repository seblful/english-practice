"""Tests for the content schema this package ships."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from practice_core.content import ContentLibrary
from practice_core.errors import ContentError
from practice_core.schema import (
    connect_content,
    content_schema,
    create_content_schema,
)

# Every table `practice_core.content` queries.
QUERIED_TABLES = frozenset(
    {
        "units",
        "exercises",
        "exercise_images",
        "questions",
        "question_answers",
        "topics",
        "unit_topics",
    }
)


def _tables(path: Path) -> set[str]:
    """Return the table names in a database."""
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in rows}


class TestContentSchema:
    def test_read_once_per_process(self) -> None:
        assert content_schema() is content_schema()

    def test_covers_every_table_the_queries_use(self, tmp_path: Path) -> None:
        """The point of shipping the schema here is that these cannot drift."""
        path = tmp_path / "content.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            create_content_schema(conn)

        assert _tables(path) >= QUERIED_TABLES

    def test_leaves_the_bot_its_own_tables(self, tmp_path: Path) -> None:
        """Authorization belongs to the bot, which creates it itself."""
        path = tmp_path / "content.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            create_content_schema(conn)

        assert "authorized_users" not in _tables(path)

    def test_applying_it_twice_is_harmless(self, tmp_path: Path) -> None:
        """`populate` and the bot both run it against the same file."""
        path = tmp_path / "content.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            create_content_schema(conn)
            create_content_schema(conn)

        assert _tables(path) >= QUERIED_TABLES

    async def test_the_queries_run_against_it(self, tmp_path: Path) -> None:
        """An empty database is a valid one: every query has to answer."""
        path = tmp_path / "content.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            create_content_schema(conn)

        library = ContentLibrary(path, read_only=True)

        assert await library.list_topics() == []
        assert await library.random_exercise() is None

    def test_a_database_that_cannot_be_written(self, tmp_path: Path) -> None:
        """The app opens its copy read-only, so this is a reachable mistake."""
        path = tmp_path / "content.db"
        path.touch()

        read_only = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        with closing(read_only), pytest.raises(ContentError, match="could not create"):
            create_content_schema(read_only)

    def test_a_schema_that_was_not_packaged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent on a packaged build means "not included", not "deleted"."""

        def missing(*_: str) -> str:
            raise FileNotFoundError("content.sql")

        monkeypatch.setattr("practice_core.schema.read_packaged_text", missing)
        content_schema.cache_clear()
        try:
            with pytest.raises(ContentError, match="not packaged"):
                content_schema()
        finally:
            content_schema.cache_clear()


class TestConnectContent:
    """The connection a writer gets has the schema's guarantees turned on."""

    def test_foreign_keys_are_enforced(self, tmp_path: Path) -> None:
        """Off by default, and per-connection: running the schema is not enough."""
        with closing(connect_content(tmp_path / "new.db", create=True)) as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_an_orphan_is_refused_at_the_write(self, tmp_path: Path) -> None:
        """This is the check `validate` used to make after the fact."""
        with (
            closing(connect_content(tmp_path / "new.db", create=True)) as conn,
            pytest.raises(sqlite3.IntegrityError),
        ):
            conn.execute(
                "INSERT INTO exercises (exercise_id, unit_id, exercise_number) "
                "VALUES ('9.9', 404, 1)"
            )

    def test_rows_come_back_by_name(self, tmp_path: Path) -> None:
        with closing(connect_content(tmp_path / "new.db", create=True)) as conn:
            conn.execute("INSERT INTO units (unit_number, title) VALUES (1, 'Present')")
            row = conn.execute("SELECT title FROM units").fetchone()

        assert row["title"] == "Present"

    def test_opening_without_creating_leaves_the_tables_alone(
        self, seeded_db_path: Path
    ) -> None:
        with closing(connect_content(seeded_db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]

        assert count > 0

    def test_a_path_that_cannot_be_opened(self, tmp_path: Path) -> None:
        with pytest.raises(ContentError, match="could not open"):
            connect_content(tmp_path / "no-such-dir" / "new.db")
