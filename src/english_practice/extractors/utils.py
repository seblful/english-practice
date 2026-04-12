"""Utility functions for extractors."""

import json
from pathlib import Path


def load_json(path: Path) -> dict:
    """Load JSON from file."""
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    """Save JSON to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_image_path(
    exercise_id: str,
    exercises_dir: Path,
    content_dir: Path,
) -> Path | None:
    """Get the image path for an exercise."""
    parts = exercise_id.split(".")
    if len(parts) != 2:
        return None

    page_num = parts[0]
    image_path = exercises_dir / page_num / f"{exercise_id}.png"

    if image_path.exists():
        return image_path

    image_path = content_dir / "exercises" / page_num / f"{exercise_id}.png"
    if image_path.exists():
        return image_path

    return None
