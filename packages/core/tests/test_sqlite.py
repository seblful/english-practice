"""Tests for running SQL off the event loop."""

import sqlite3
from pathlib import Path

import pytest

from practice_core.errors import ContentError
from practice_core.sqlite import SqliteStore


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    """A store over a file with one table in it."""
    path = tmp_path / "scratch.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.execute("INSERT INTO notes (id, body) VALUES (1, 'first'), (2, 'second')")
    conn.close()
    return SqliteStore(path)


class TestReading:
    async def test_rows_returns_every_match(self, store: SqliteStore) -> None:
        rows = await store.rows("SELECT body FROM notes ORDER BY id")

        assert [row["body"] for row in rows] == ["first", "second"]

    async def test_row_returns_the_first(self, store: SqliteStore) -> None:
        row = await store.row("SELECT body FROM notes WHERE id = ?", (2,))

        assert row is not None
        assert row["body"] == "second"

    async def test_row_returns_none_when_there_is_no_match(
        self, store: SqliteStore
    ) -> None:
        assert await store.row("SELECT body FROM notes WHERE id = ?", (99,)) is None


class TestWriting:
    async def test_execute_commits(self, store: SqliteStore) -> None:
        await store.execute("INSERT INTO notes (id, body) VALUES (?, ?)", (3, "third"))

        assert len(await store.rows("SELECT id FROM notes")) == 3

    async def test_script_runs_several_statements(self, store: SqliteStore) -> None:
        await store.script(
            "CREATE TABLE IF NOT EXISTS tags (name TEXT);"
            "INSERT INTO tags (name) VALUES ('a');"
        )

        assert len(await store.rows("SELECT name FROM tags")) == 1

    async def test_a_failed_statement_rolls_back(self, store: SqliteStore) -> None:
        with pytest.raises(ContentError):
            await store.execute("INSERT INTO notes (id, body) VALUES (1, 'clash')")

        assert len(await store.rows("SELECT id FROM notes")) == 2


class TestReadOnly:
    async def test_refuses_to_write(self, tmp_path: Path, store: SqliteStore) -> None:
        """The guarantee the app relies on: its copy ships inside the APK."""
        sealed = SqliteStore(store.db_path, read_only=True)

        with pytest.raises(ContentError, match="could not be read"):
            await sealed.execute("DELETE FROM notes")

    async def test_a_missing_file_names_itself(self, tmp_path: Path) -> None:
        """SQLite's own message for this says nothing about what to do next."""
        sealed = SqliteStore(tmp_path / "absent.db", read_only=True)

        with pytest.raises(ContentError, match=r"absent.db"):
            await sealed.rows("SELECT 1")
