"""Tests for extractor utility functions."""

import json
from pathlib import Path

import pytest

from src.english_practice.extractors.utils import get_image_path, load_json, save_json


class TestLoadJson:
    """Tests for load_json."""

    def test_loads_existing_file(self, tmp_path) -> None:
        data = {"key": "value"}
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert load_json(path) == data

    def test_invalid_json(self, tmp_path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_json(path)


class TestSaveJson:
    """Tests for save_json."""

    def test_saves_to_file(self, tmp_path) -> None:
        data = {"key": "value"}
        path = tmp_path / "subdir" / "test.json"
        save_json(path, data)
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == data

    def test_overwrites_existing(self, tmp_path) -> None:
        path = tmp_path / "test.json"
        path.write_text('{"old": true}', encoding="utf-8")
        save_json(path, {"new": True})
        assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}


class TestGetImagePath:
    """Tests for get_image_path."""

    def test_finds_in_exercises_dir(self, tmp_path) -> None:
        exercises_dir = tmp_path / "exercises"
        content_dir = tmp_path / "content"
        img_path = exercises_dir / "1" / "1.1.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_text("img")

        result = get_image_path("1.1", exercises_dir, content_dir)
        assert result == img_path

    def test_finds_in_content_dir(self, tmp_path) -> None:
        exercises_dir = tmp_path / "exercises"
        content_dir = tmp_path / "content"
        img_path = content_dir / "exercises" / "1" / "1.1.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_text("img")

        result = get_image_path("1.1", exercises_dir, content_dir)
        assert result == img_path

    def test_returns_none_when_not_found(self, tmp_path) -> None:
        result = get_image_path("99.99", tmp_path / "exercises", tmp_path / "content")
        assert result is None

    def test_returns_none_for_invalid_exercise_id(self, tmp_path) -> None:
        result = get_image_path("invalid", tmp_path / "exercises", tmp_path / "content")
        assert result is None

    def test_prefers_exercises_dir_over_content(self, tmp_path) -> None:
        exercises_dir = tmp_path / "exercises"
        content_dir = tmp_path / "content"

        img1 = exercises_dir / "1" / "1.1.png"
        img1.parent.mkdir(parents=True)
        img1.write_text("exercises_version")

        img2 = content_dir / "exercises" / "1" / "1.1.png"
        img2.parent.mkdir(parents=True)
        img2.write_text("content_version")

        result = get_image_path("1.1", exercises_dir, content_dir)
        assert result == img1
        assert result.read_bytes() == b"exercises_version"
