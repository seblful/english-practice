"""Building the exercise database that ships inside the Android app."""

import io
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from practice_core.errors import ContentError
from practice_core.schema import connect_content
from practice_runtime.logging import get_logger

logger = get_logger(__name__)

__all__ = ["BundleResult", "build_mobile_content"]

# A phone reads these crops at ~1080px wide; beyond that is detail nobody sees.
MAX_IMAGE_WIDTH = 1100
WEBP_QUALITY = 80
WEBP_METHOD = 4

# Tables copied verbatim, parents before children so the foreign keys hold.
_CONTENT_TABLES = (
    "units",
    "topics",
    "unit_topics",
    "exercises",
    "questions",
    "question_answers",
)

_SIZE_SIDECAR_SUFFIX = ".size"


@dataclass(frozen=True, slots=True)
class BundleResult:
    """What a bundling run produced."""

    path: Path
    images: int
    source_bytes: int
    bundled_bytes: int

    @property
    def ratio(self) -> float:
        """Return the bundled image size as a fraction of the original."""
        return self.bundled_bytes / self.source_bytes if self.source_bytes else 0.0

    def summary(self) -> str:
        """Return a one-line report of the run."""
        # ASCII only: a cp1252 console raises rather than printing an em dash.
        return (
            f"{self.path}: {self.path.stat().st_size / 1_048_576:.1f} MB total, "
            f"{self.images} images "
            f"({self.source_bytes / 1_048_576:.1f} MB -> "
            f"{self.bundled_bytes / 1_048_576:.1f} MB, "
            f"{self.ratio:.0%} of the original)"
        )


def shrink_image(data: bytes) -> bytes:
    """Re-encode one exercise image for the app bundle."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            converted = image.convert("RGB")
            width, height = converted.size
            if width > MAX_IMAGE_WIDTH:
                scaled = round(height * MAX_IMAGE_WIDTH / width)
                converted = converted.resize(
                    (MAX_IMAGE_WIDTH, scaled), Image.Resampling.LANCZOS
                )

            buffer = io.BytesIO()
            converted.save(buffer, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    except OSError:
        # Returned by identity, so :func:`_copy_images` can name the row it warns of.
        return data
    return buffer.getvalue()


def _copy_table(
    source: sqlite3.Connection, target: sqlite3.Connection, table: str
) -> int:
    """Copy one table verbatim."""
    rows = source.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    names = list(rows[0].keys())
    columns = ", ".join(names)
    placeholders = ", ".join("?" for _ in names)
    target.executemany(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        [tuple(row) for row in rows],
    )
    return len(rows)


def _copy_images(
    source: sqlite3.Connection, target: sqlite3.Connection
) -> tuple[int, int, int]:
    """Copy every exercise image, re-encoding as it goes."""
    count = 0
    source_bytes = 0
    bundled_bytes = 0

    for row in source.execute(
        "SELECT id, exercise_id, image_data FROM exercise_images ORDER BY id"
    ):
        original: bytes = row["image_data"]
        if not original:
            # The app treats a zero-length blob as no image; carrying it gains nothing.
            continue

        shrunk = shrink_image(original)
        if shrunk is original:
            logger.warning(
                "bundle_image_unreadable",
                image_id=row["id"],
                exercise_id=row["exercise_id"],
                bytes=len(original),
            )
        target.execute(
            "INSERT INTO exercise_images (id, exercise_id, image_data) "
            "VALUES (?, ?, ?)",
            (row["id"], row["exercise_id"], shrunk),
        )
        count += 1
        source_bytes += len(original)
        bundled_bytes += len(shrunk)

    return count, source_bytes, bundled_bytes


def build_mobile_content(
    source_path: Path,
    target_path: Path,
    *,
    progress: Callable[[str], None] | None = None,
) -> BundleResult:
    """Write a compact copy of the exercise database for the app bundle."""
    if not source_path.exists():
        raise ContentError(
            f"No exercise database at {source_path}. "
            "Run `practice-content populate` first."
        )

    def say(message: str) -> None:
        if progress is not None:
            progress(message)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.unlink(missing_ok=True)

    with (
        closing(
            sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        ) as source,
        # The same schema and enforcement, so a missing table fails as an insert.
        closing(connect_content(target_path, create=True)) as target,
    ):
        source.row_factory = sqlite3.Row

        with target:
            for table in _CONTENT_TABLES:
                copied = _copy_table(source, target, table)
                say(f"  {table}: {copied} rows")

            say("  re-encoding images...")
            images, source_bytes, bundled_bytes = _copy_images(source, target)

        # VACUUM cannot run in a transaction, and without it the pages stay claimed.
        target.execute("VACUUM")

    result = BundleResult(
        path=target_path,
        images=images,
        source_bytes=source_bytes,
        bundled_bytes=bundled_bytes,
    )

    # The app reads this to tell "already unpacked" from "the bundle changed".
    sidecar = target_path.with_name(f"{target_path.name}{_SIZE_SIDECAR_SUFFIX}")
    sidecar.write_text(str(target_path.stat().st_size), encoding="utf-8")

    logger.info(
        "mobile_content_built",
        path=str(target_path),
        images=images,
        bundled_bytes=bundled_bytes,
    )
    return result
