"""Tests for building the exercise database that ships inside the app."""

import io
import random
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

import pytest
from PIL import Image
from practice_core.errors import ContentError
from practice_core.schema import create_content_schema

from practice_extraction.bundle import (
    MAX_IMAGE_WIDTH,
    build_mobile_content,
    shrink_image,
)


@lru_cache(maxsize=8)
def _png(width: int, height: int) -> bytes:
    """Return a PNG of a given size, roughly as a scanned page compresses."""
    noise = random.Random(20260314)
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        shade = 200 + int(40 * y / max(1, height))
        for x in range(width):
            jitter = noise.randint(-25, 25)
            value = max(0, min(255, shade + jitter))
            pixels[x, y] = (value, value, min(255, value + 5))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    """A small database in the shape ``populate.py`` writes."""
    path = tmp_path / "source.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        create_content_schema(conn)
        conn.executescript(
            """
            INSERT INTO units (id, unit_number, title)
            VALUES (1, 1, 'Present Continuous');

            INSERT INTO topics (id, name) VALUES (1, 'Present Tenses');

            INSERT INTO unit_topics (unit_id, topic_id) VALUES (1, 1);

            INSERT INTO exercises (id, exercise_id, unit_id, exercise_number)
            VALUES (1, '1.1', 1, 1), (2, '1.2', 1, 2),
                   (3, '1.3', 1, 3), (4, '1.4', 1, 4);

            INSERT INTO questions (id, exercise_id, question_id, rule)
            VALUES (1, 1, '1', 'Use present continuous'),
                   (2, 2, '1', NULL);

            INSERT INTO question_answers (question_id, short_answer, full_answer)
            VALUES (1, 'is doing', 'He is doing.');
            """
        )
        conn.execute(
            "INSERT INTO exercise_images (exercise_id, image_data) VALUES (?, ?)",
            (1, _png(2051, 700)),
        )
        conn.execute(
            "INSERT INTO exercise_images (exercise_id, image_data) VALUES (?, ?)",
            (2, _png(400, 200)),
        )
        conn.execute(
            "INSERT INTO exercise_images (exercise_id, image_data) VALUES (?, ?)",
            (3, b""),
        )
        conn.execute(
            "INSERT INTO exercise_images (exercise_id, image_data) VALUES (?, ?)",
            (4, b"not an image at all"),
        )
    return path


class TestShrinkImage:
    def test_a_wide_image_is_scaled_down(self) -> None:
        shrunk = shrink_image(_png(2051, 700))

        with Image.open(io.BytesIO(shrunk)) as image:
            assert image.width == MAX_IMAGE_WIDTH
            assert image.format == "WEBP"

    def test_a_narrow_image_keeps_its_size(self) -> None:
        shrunk = shrink_image(_png(400, 200))

        with Image.open(io.BytesIO(shrunk)) as image:
            assert image.size == (400, 200)

    def test_the_aspect_ratio_is_kept(self) -> None:
        shrunk = shrink_image(_png(2000, 500))

        with Image.open(io.BytesIO(shrunk)) as image:
            assert image.height == round(500 * MAX_IMAGE_WIDTH / 2000)

    def test_a_book_page_shrinks_substantially(self) -> None:
        """The whole point is fitting two hundred megabytes into an APK."""
        original = _png(2051, 700)

        assert len(shrink_image(original)) < len(original) / 2

    def test_something_that_is_not_an_image_is_passed_through(self) -> None:
        """One bad row costs one large image, not the whole bundle."""
        assert shrink_image(b"not an image") == b"not an image"


class TestBuildMobileContent:
    def test_it_copies_every_content_row(self, source_db: Path, tmp_path: Path) -> None:
        target = tmp_path / "bundle" / "content.db"

        build_mobile_content(source_db, target)

        with closing(sqlite3.connect(target)) as conn:
            counts = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "units",
                    "topics",
                    "unit_topics",
                    "exercises",
                    "questions",
                    "question_answers",
                )
            }

        assert counts == {
            "units": 1,
            "topics": 1,
            "unit_topics": 1,
            "exercises": 4,
            "questions": 2,
            "question_answers": 1,
        }

    def test_the_ids_are_preserved(self, source_db: Path, tmp_path: Path) -> None:
        """The app runs the shared queries against this file unmodified."""
        target = tmp_path / "content.db"

        build_mobile_content(source_db, target)

        with closing(sqlite3.connect(target)) as conn:
            row = conn.execute(
                "SELECT exercise_id FROM exercises WHERE id = 3"
            ).fetchone()

        assert row[0] == "1.3"

    def test_the_images_are_re_encoded(self, source_db: Path, tmp_path: Path) -> None:
        target = tmp_path / "content.db"

        result = build_mobile_content(source_db, target)

        with closing(sqlite3.connect(target)) as conn:
            blob = conn.execute(
                "SELECT image_data FROM exercise_images WHERE exercise_id = 1"
            ).fetchone()[0]

        with Image.open(io.BytesIO(blob)) as image:
            assert image.format == "WEBP"
        assert result.bundled_bytes < result.source_bytes
        assert 0 < result.ratio < 1

    def test_empty_blobs_are_dropped(self, source_db: Path, tmp_path: Path) -> None:
        """The app treats a zero-length blob as no image, so it is dead weight."""
        target = tmp_path / "content.db"

        result = build_mobile_content(source_db, target)

        with closing(sqlite3.connect(target)) as conn:
            present = {
                row[0]
                for row in conn.execute("SELECT exercise_id FROM exercise_images")
            }

        assert present == {1, 2, 4}
        assert result.images == 3

    def test_it_writes_the_size_sidecar(self, source_db: Path, tmp_path: Path) -> None:
        """The app reads this to tell an unpacked copy from a stale one."""
        target = tmp_path / "content.db"

        build_mobile_content(source_db, target)

        sidecar = target.with_name(f"{target.name}.size")
        assert int(sidecar.read_text(encoding="utf-8")) == target.stat().st_size

    def test_it_overwrites_a_previous_bundle(
        self, source_db: Path, tmp_path: Path
    ) -> None:
        target = tmp_path / "content.db"
        target.write_bytes(b"stale")

        build_mobile_content(source_db, target)

        with closing(sqlite3.connect(target)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 1

    def test_it_reports_progress_when_asked(
        self, source_db: Path, tmp_path: Path
    ) -> None:
        lines: list[str] = []

        build_mobile_content(source_db, tmp_path / "content.db", progress=lines.append)

        assert any("units" in line for line in lines)
        assert any("re-encoding" in line for line in lines)

    def test_the_summary_names_the_file_and_the_saving(
        self, source_db: Path, tmp_path: Path
    ) -> None:
        result = build_mobile_content(source_db, tmp_path / "content.db")

        summary = result.summary()

        assert "content.db" in summary
        assert "3 images" in summary
        # The console this reaches may be on a cp1252 code page.
        assert summary.isascii()

    def test_a_missing_source_says_how_to_build_one(self, tmp_path: Path) -> None:
        with pytest.raises(ContentError, match="practice-content populate"):
            build_mobile_content(tmp_path / "absent.db", tmp_path / "out.db")

    def test_an_empty_source_produces_an_empty_bundle(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.db"
        with closing(sqlite3.connect(empty)) as conn, conn:
            create_content_schema(conn)
        target = tmp_path / "content.db"

        result = build_mobile_content(empty, target)

        assert result.images == 0
        assert result.ratio == 0.0
        assert target.is_file()
