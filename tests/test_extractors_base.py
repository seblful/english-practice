"""Tests for BaseExtractor."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from src.english_practice.extractors.base_extractor import BaseExtractor


class _UnitModel(BaseModel):
    unit_id: str


class _OutputModel(BaseModel):
    units: list[_UnitModel] = []


class _ConcreteExtractor(BaseExtractor):
    """Concrete subclass for testing."""

    async def _process_unit(self, unit: dict) -> _UnitModel:
        return _UnitModel(unit_id=unit["unit_id"])


@pytest.fixture
def extractor(tmp_path) -> _ConcreteExtractor:
    """Create a concrete extractor with temp paths."""
    output_path = tmp_path / "output.json"
    answers_path = tmp_path / "answers.json"
    exercises_dir = tmp_path / "exercises"
    content_dir = tmp_path / "content"
    exercises_dir.mkdir(parents=True)
    content_dir.mkdir(parents=True)
    return _ConcreteExtractor(output_path, answers_path, exercises_dir, content_dir)


class TestBaseExtractor:
    """Tests for BaseExtractor."""

    def test_init_loads_topic_map(self, tmp_path) -> None:
        metadata_dir = tmp_path / "content" / "metadata"
        metadata_dir.mkdir(parents=True)
        topic_file = metadata_dir / "topic_to_unit.json"
        topic_file.write_text(
            json.dumps([{"topic": "Present Tenses", "unit_ids": [1, 2]}])
        )

        ext = _ConcreteExtractor(
            tmp_path / "out.json",
            tmp_path / "answers.json",
            tmp_path / "exercises",
            tmp_path / "content",
        )
        assert ext._get_topic_name("1") == "Present Tenses"
        assert ext._get_topic_name("2") == "Present Tenses"

    def test_get_topic_name_default(self, extractor) -> None:
        assert extractor._get_topic_name("999") == "Unknown Topic"

    def test_get_topic_name_empty_map(self, tmp_path) -> None:
        ext = _ConcreteExtractor(
            tmp_path / "out.json",
            tmp_path / "answers.json",
            tmp_path / "exercises",
            tmp_path / "content",
        )
        assert ext._get_topic_name("1") == "Unknown Topic"

    def test_get_image_path_finds_in_exercises_dir(self, extractor) -> None:
        img_path = extractor._exercises_dir / "1" / "1.1.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_text("img")
        assert extractor._get_image_path("1.1") == img_path

    def test_get_image_path_finds_in_content_dir(self, extractor) -> None:
        img_path = extractor._content_dir / "exercises" / "1" / "1.1.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_text("img")
        assert extractor._get_image_path("1.1") == img_path

    def test_get_image_path_not_found(self, extractor) -> None:
        assert extractor._get_image_path("99.99") is None

    def test_get_image_path_invalid_id(self, extractor) -> None:
        assert extractor._get_image_path("invalid") is None

    def test_load_answers_data_returns_empty_if_missing(self, extractor) -> None:
        assert extractor._load_answers_data() == {}

    def test_load_answers_data_loads_json(self, extractor) -> None:
        data = {"units": [{"unit_id": "1"}]}
        extractor._answers_path.write_text(json.dumps(data))
        assert extractor._load_answers_data() == data

    def test_load_output_returns_empty_if_missing(self, extractor) -> None:
        result = extractor._load_output(_OutputModel)
        assert result.units == []

    def test_load_output_loads_existing(self, extractor) -> None:
        output = _OutputModel(units=[_UnitModel(unit_id="1")])
        extractor._output_path.write_text(output.model_dump_json(indent=2))
        result = extractor._load_output(_OutputModel)
        assert len(result.units) == 1
        assert result.units[0].unit_id == "1"

    def test_save_output_creates_file(self, extractor) -> None:
        output = _OutputModel(units=[_UnitModel(unit_id="1")])
        extractor._save_output(output)
        assert extractor._output_path.exists()

    def test_is_unit_processed(self, extractor) -> None:
        output = _OutputModel(units=[_UnitModel(unit_id="1")])
        assert extractor._is_unit_processed(output, "1") is True
        assert extractor._is_unit_processed(output, "2") is False

    def test_add_unit(self, extractor) -> None:
        output = _OutputModel()
        extractor._add_unit(output, _UnitModel(unit_id="1"))
        assert len(output.units) == 1

    @pytest.mark.asyncio
    async def test_extract_processes_all_units(self, extractor) -> None:
        data = {"units": [{"unit_id": "1"}, {"unit_id": "2"}]}
        extractor._answers_path.write_text(json.dumps(data))
        result = await extractor.extract(_OutputModel)
        assert result == {"output_path": extractor._output_path}
        assert extractor._output_path.exists()

    @pytest.mark.asyncio
    async def test_extract_skips_processed_units(self, extractor) -> None:
        data = {"units": [{"unit_id": "1"}]}
        extractor._answers_path.write_text(json.dumps(data))
        output = _OutputModel(units=[_UnitModel(unit_id="1")])
        extractor._output_path.write_text(output.model_dump_json(indent=2))
        result = await extractor.extract(_OutputModel)
        assert result == {"output_path": extractor._output_path}

    def test_process_unit_raises_not_implemented(self, tmp_path) -> None:
        from src.english_practice.extractors.base_extractor import BaseExtractor
        ext = BaseExtractor(
            tmp_path / "out.json",
            tmp_path / "answers.json",
            tmp_path / "exercises",
            tmp_path / "content",
        )
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.run(ext._process_unit({"unit_id": "1"}))
