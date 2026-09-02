"""Tests for the storage paths and unpacking the bundled database.

The Android case — the database inside a zip that only ``zipimport`` can read —
is reproduced with a real zip, because that is the whole point of the code
under test.
"""

import shutil
import zipfile
from pathlib import Path

import pytest
from practice_core.errors import ContentError

from practice.storage import (
    CONTENT_DB_NAME,
    SIZE_SIDECAR_SUFFIX,
    bundled_content_dir,
    ensure_content_database,
    stats_database_path,
    storage_dir,
)

DB_BYTES = b"SQLite format 3\x00" + b"\x00" * 200


def _packaged_dir(root: Path, *, sidecar: bool = True) -> Path:
    """Write a fake packaged content directory on disk.

    Args:
        root: Where to create it.
        sidecar: Whether to write the size sidecar next to the database.

    Returns:
        The directory.
    """
    directory = root / "packaged"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / CONTENT_DB_NAME).write_bytes(DB_BYTES)
    if sidecar:
        (directory / f"{CONTENT_DB_NAME}{SIZE_SIDECAR_SUFFIX}").write_text(
            str(len(DB_BYTES)), encoding="utf-8"
        )
    return directory


def _zipped_dir(root: Path, *, sidecar: bool = True) -> zipfile.Path:
    """Return a content directory that lives inside a zip.

    Args:
        root: Where to write the archive.
        sidecar: Whether to include the size sidecar.

    Returns:
        A traversable pointing inside the archive, as ``zipimport`` hands one
        to :mod:`importlib.resources` on Android.
    """
    archive = root / "app.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(f"content/{CONTENT_DB_NAME}", DB_BYTES)
        if sidecar:
            zipped.writestr(
                f"content/{CONTENT_DB_NAME}{SIZE_SIDECAR_SUFFIX}", str(len(DB_BYTES))
            )
    return zipfile.Path(archive) / "content"


class TestStorageDir:
    def test_follows_the_flet_environment_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "app-data"
        monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(target))

        assert storage_dir() == target
        assert target.is_dir()

    def test_falls_back_to_a_local_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A test or a script runs outside a Flet app and must still work."""
        monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
        monkeypatch.chdir(tmp_path)

        assert storage_dir().is_dir()

    def test_the_progress_database_sits_in_the_storage_directory(
        self, tmp_path: Path
    ) -> None:
        assert stats_database_path(tmp_path).parent == tmp_path

    def test_the_progress_database_defaults_to_the_storage_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))

        assert stats_database_path().parent == tmp_path


class TestBundledContentDir:
    def test_resolves_inside_the_installed_package(self) -> None:
        assert bundled_content_dir().name == "content"


class TestEnsureContentDatabase:
    def test_a_real_file_is_used_where_it_lies(self, tmp_path: Path) -> None:
        """Desktop, and an Android build that ships the package extracted."""
        packaged = _packaged_dir(tmp_path)
        storage = tmp_path / "storage"

        resolved = ensure_content_database(storage, packaged)

        assert resolved == packaged / CONTENT_DB_NAME
        assert not storage.exists()

    def test_a_zipped_database_is_unpacked_once(self, tmp_path: Path) -> None:
        zipped = _zipped_dir(tmp_path)
        storage = tmp_path / "storage"

        resolved = ensure_content_database(storage, zipped)

        assert resolved == storage / CONTENT_DB_NAME
        assert resolved.read_bytes() == DB_BYTES

    def test_a_second_launch_reuses_the_unpacked_copy(self, tmp_path: Path) -> None:
        zipped = _zipped_dir(tmp_path)
        storage = tmp_path / "storage"
        first = ensure_content_database(storage, zipped)
        stamp = first.stat().st_mtime_ns

        second = ensure_content_database(storage, zipped)

        assert second == first
        assert second.stat().st_mtime_ns == stamp

    def test_a_changed_bundle_is_unpacked_again(self, tmp_path: Path) -> None:
        """The sidecar is what tells "already unpacked" from "new content"."""
        zipped = _zipped_dir(tmp_path)
        storage = tmp_path / "storage"
        target = storage / CONTENT_DB_NAME
        storage.mkdir(parents=True)
        target.write_bytes(b"stale")

        resolved = ensure_content_database(storage, zipped)

        assert resolved.read_bytes() == DB_BYTES

    def test_without_a_sidecar_an_existing_copy_is_trusted(
        self, tmp_path: Path
    ) -> None:
        zipped = _zipped_dir(tmp_path, sidecar=False)
        storage = tmp_path / "storage"
        storage.mkdir(parents=True)
        (storage / CONTENT_DB_NAME).write_bytes(b"whatever is there")

        resolved = ensure_content_database(storage, zipped)

        assert resolved.read_bytes() == b"whatever is there"

    def test_an_unreadable_sidecar_is_ignored(self, tmp_path: Path) -> None:
        archive = tmp_path / "app.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(f"content/{CONTENT_DB_NAME}", DB_BYTES)
            zipped.writestr(
                f"content/{CONTENT_DB_NAME}{SIZE_SIDECAR_SUFFIX}", "not a number"
            )
        storage = tmp_path / "storage"

        resolved = ensure_content_database(storage, zipfile.Path(archive) / "content")

        assert resolved.read_bytes() == DB_BYTES

    def test_a_bundle_with_no_database_says_how_to_build_one(
        self, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(ContentError, match="mobile-content"):
            ensure_content_database(tmp_path / "storage", empty)

    def test_the_unpack_leaves_no_temporary_files_behind(self, tmp_path: Path) -> None:
        zipped = _zipped_dir(tmp_path)
        storage = tmp_path / "storage"

        ensure_content_database(storage, zipped)

        assert [path.name for path in storage.iterdir()] == [CONTENT_DB_NAME]


class TestUnpackFailures:
    def test_an_unwritable_target_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A phone that has run out of space must say so, not crash."""

        def full_disk(*_: object, **__: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(shutil, "copyfileobj", full_disk)

        with pytest.raises(ContentError, match="could not be unpacked"):
            ensure_content_database(tmp_path / "storage", _zipped_dir(tmp_path))

    def test_a_failed_unpack_leaves_nothing_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def full_disk(*_: object, **__: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(shutil, "copyfileobj", full_disk)
        storage = tmp_path / "storage"

        with pytest.raises(ContentError):
            ensure_content_database(storage, _zipped_dir(tmp_path))

        assert list(storage.iterdir()) == []
