"""Tests for the record of who may use the bot, against a real file.

The content queries are not re-tested here. They belong to
:class:`practice_core.content.ContentLibrary`, which has its own suite over its
own seed; this repository used to inherit them, so thirteen of them were
asserted twice against two copies of the same fixture data.
"""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from practice_core.errors import ContentError
from practice_core.schema import create_content_schema

from practice_bot.repositories.database import AUTH_SCHEMA, AuthRepository


@pytest.fixture
def db_path(seeded_db_path: Path) -> Path:
    """The seeded database, under the name these tests use."""
    return seeded_db_path


@pytest.fixture
def repository(db_path: Path) -> AuthRepository:
    """A repository pointed at the seeded database."""
    return AuthRepository(db_path)


class TestEnsureSchema:
    """The bot creates its own table; the pipeline builds the content ones."""

    @pytest.fixture
    def content_only(self, tmp_path: Path) -> Path:
        """A database as `populate` leaves it: content tables, nothing else."""
        path = tmp_path / "content-only.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            create_content_schema(conn)
        return path

    def _tables(self, path: Path) -> set[str]:
        with closing(sqlite3.connect(path)) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return {row[0] for row in rows}

    async def test_creates_the_table_a_fresh_database_lacks(
        self, content_only: Path
    ) -> None:
        assert "authorized_users" not in self._tables(content_only)

        await AuthRepository(content_only).ensure_schema()

        assert "authorized_users" in self._tables(content_only)

    async def test_a_database_that_already_has_it_is_untouched(
        self, repository: AuthRepository
    ) -> None:
        """Every startup runs this, including the ones after the first."""
        await repository.register_user(1, "Alice", "alice")

        await repository.ensure_schema()

        assert await repository.get_auth_status(1) == "pending"

    async def test_the_created_table_takes_a_registration(
        self, content_only: Path
    ) -> None:
        repository = AuthRepository(content_only)
        await repository.ensure_schema()

        await repository.register_user(7, "Bob", None)

        assert await repository.get_auth_status(7) == "pending"

    async def test_a_schema_that_was_not_packaged(
        self, repository: AuthRepository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Absent on a packaged build means "not included", not "deleted"."""

        def missing(*_: str) -> str:
            raise FileNotFoundError(AUTH_SCHEMA)

        monkeypatch.setattr(
            "practice_bot.repositories.database.read_packaged_text", missing
        )

        with pytest.raises(ContentError, match="not packaged"):
            await repository.ensure_schema()


class TestAuthorization:
    """Tests for the access-control tables."""

    async def test_unknown_user_has_no_status(self, repository: AuthRepository) -> None:
        assert await repository.get_auth_status(1) is None

    async def test_registering_starts_as_pending(
        self, repository: AuthRepository
    ) -> None:
        await repository.register_user(1, "Alice", "alice")

        assert await repository.get_auth_status(1) == "pending"

    async def test_registering_twice_keeps_the_first_record(
        self, repository: AuthRepository
    ) -> None:
        await repository.register_user(1, "Alice", "alice")
        await repository.set_auth_status(1, "approved", handled_by=9)
        await repository.register_user(1, "Alice", "alice")

        assert await repository.get_auth_status(1) == "approved"

    async def test_approving_and_rejecting(self, repository: AuthRepository) -> None:
        await repository.register_user(1, "Alice", None)

        await repository.set_auth_status(1, "approved", handled_by=9)
        assert await repository.get_auth_status(1) == "approved"

        await repository.set_auth_status(1, "rejected", handled_by=9)
        assert await repository.get_auth_status(1) == "rejected"

    async def test_reset_to_pending_clears_the_decision(
        self, repository: AuthRepository, db_path: Path
    ) -> None:
        await repository.register_user(1, "Alice", "alice")
        await repository.set_auth_status(1, "rejected", handled_by=9)

        await repository.reset_to_pending(1, "Alice Updated", "alice2")

        assert await repository.get_auth_status(1) == "pending"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT full_name, telegram_username, handled_at, handled_by "
                "FROM authorized_users WHERE telegram_id = 1"
            ).fetchone()
        assert row == ("Alice Updated", "alice2", None, None)

    async def test_pending_queue_is_oldest_first_and_excludes_decided(
        self, repository: AuthRepository, db_path: Path
    ) -> None:
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.executescript(
                """
                INSERT INTO authorized_users
                    (telegram_id, full_name, telegram_username, status, created_at)
                VALUES (1, 'Alice', 'alice', 'pending', '2026-01-01'),
                       (2, 'Bob', NULL, 'pending', '2026-01-02'),
                       (3, 'Carol', NULL, 'approved', '2026-01-03');
                """
            )

        pending = await repository.list_pending_users()

        assert [user.full_name for user in pending] == ["Alice", "Bob"]
        assert pending[0].label == "Alice (@alice)"
        assert pending[1].label == "Bob"


class TestConnectionHandling:
    """A bot that leaks connections dies slowly; assert it does not."""

    async def test_connections_are_closed(
        self, repository: AuthRepository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`with sqlite3.connect(...)` commits but does not close — so we must."""
        opened = 0
        closed = 0
        real_connect = sqlite3.connect

        class TrackingConnection(sqlite3.Connection):
            def close(self) -> None:
                nonlocal closed
                closed += 1
                super().close()

        def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
            nonlocal opened
            opened += 1
            kwargs["factory"] = TrackingConnection
            return real_connect(*args, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", tracking_connect)

        await repository.register_user(1, "Alice", None)
        await repository.get_auth_status(1)

        assert opened == 2
        assert closed == opened

    async def test_write_is_committed(self, repository: AuthRepository) -> None:
        await repository.register_user(1, "Alice", None)

        # A fresh repository sees only committed data.
        assert await AuthRepository(repository.db_path).get_auth_status(1) == (
            "pending"
        )

    async def test_the_file_is_the_one_it_was_handed(self, db_path: Path) -> None:
        """It used to read process-wide settings from inside its constructor."""
        assert AuthRepository(db_path).db_path == db_path
