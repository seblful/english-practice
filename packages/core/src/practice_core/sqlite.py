"""Running SQL against a SQLite file, off the event loop."""

import asyncio
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from practice_core.errors import ContentError

__all__ = ["BUSY_TIMEOUT_SECONDS", "SqlParams", "SqliteStore"]

# Waiting beats failing when another writer holds the lock: bot writes are tiny.
BUSY_TIMEOUT_SECONDS = 5.0

SqlParams = Sequence[Any]


class SqliteStore:
    """One SQLite file, read and written from async code."""

    def __init__(self, db_path: Path, *, read_only: bool = False) -> None:
        """Initialize the store."""
        self.db_path = db_path
        self.read_only = read_only

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection that commits on success and always closes."""
        if self.read_only and not self.db_path.exists():
            raise ContentError(f"The exercise database is missing at {self.db_path}.")

        try:
            with closing(self._open()) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                with conn:  # commits on success, rolls back on exception
                    yield conn
        except sqlite3.Error as exc:
            raise ContentError(
                f"The exercise database could not be read: {exc}"
            ) from exc

    def _open(self) -> sqlite3.Connection:
        """Open the database, honouring :attr:`read_only`."""
        if self.read_only:
            return sqlite3.connect(
                f"file:{self.db_path.as_posix()}?mode=ro",
                uri=True,
                timeout=BUSY_TIMEOUT_SECONDS,
            )
        return sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_SECONDS)

    def _query_sync(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query and return every row."""
        with self.connect() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def _execute_sync(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement."""
        with self.connect() as conn:
            conn.execute(sql, tuple(params))

    def _script_sync(self, sql: str) -> None:
        """Run a multi-statement script."""
        with self.connect() as conn:
            conn.executescript(sql)

    async def rows(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        """Run a read query off the event loop."""
        return await asyncio.to_thread(self._query_sync, sql, params)

    async def row(self, sql: str, params: SqlParams = ()) -> sqlite3.Row | None:
        """Run a read query off the event loop and return the first row."""
        found = await self.rows(sql, params)
        return found[0] if found else None

    async def execute(self, sql: str, params: SqlParams = ()) -> None:
        """Run a write statement off the event loop."""
        await asyncio.to_thread(self._execute_sync, sql, params)

    async def script(self, sql: str) -> None:
        """Run a multi-statement script off the event loop."""
        await asyncio.to_thread(self._script_sync, sql)
