"""Tests for BaseExtractor."""

import asyncio
import json

import pytest
from practice_runtime.errors import ConfigurationError
from pydantic import BaseModel

from practice_extraction.extractors.base_extractor import BaseExtractor
from tests.conftest import extraction_paths


class _UnitModel(BaseModel):
    unit_id: str


class _OutputModel(BaseModel):
    units: list[_UnitModel] = []


class _ConcreteExtractor(BaseExtractor):
    """Concrete subclass for testing."""

    OUTPUT_FILENAME = "output.json"

    async def _process_unit(self, unit: dict) -> _UnitModel:
        return _UnitModel(unit_id=unit["unit_id"])


@pytest.fixture
def extractor(tmp_path) -> _ConcreteExtractor:
    """Create a concrete extractor over a temporary content layout."""
    return _ConcreteExtractor(extraction_paths(tmp_path))


class TestBaseExtractor:
    """Tests for BaseExtractor."""

    def test_init_loads_topic_map(self, tmp_path) -> None:
        paths = extraction_paths(tmp_path)
        (paths.metadata_dir / "topic_to_unit.json").write_text(
            json.dumps([{"topic": "Present Tenses", "unit_ids": [1, 2]}])
        )

        ext = _ConcreteExtractor(paths)

        assert ext._get_topic_name("1") == "Present Tenses"
        assert ext._get_topic_name("2") == "Present Tenses"

    def test_get_topic_name_default(self, extractor) -> None:
        assert extractor._get_topic_name("999") == "Unknown Topic"

    def test_get_topic_name_empty_map(self, extractor) -> None:
        assert extractor._get_topic_name("1") == "Unknown Topic"

    def test_get_image_path_finds_the_exercise_image(self, extractor) -> None:
        img_path = extractor._paths.exercises_dir / "1" / "1.1.png"
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

    @pytest.mark.asyncio
    async def test_extract_processes_all_units(self, extractor) -> None:
        data = {"units": [{"unit_id": "1"}, {"unit_id": "2"}]}
        extractor._answers_path.write_text(json.dumps(data))
        result = await extractor._extract_units(_OutputModel)
        assert result == extractor._output_path
        assert extractor._output_path.exists()

    @pytest.mark.asyncio
    async def test_extract_skips_processed_units(self, extractor) -> None:
        data = {"units": [{"unit_id": "1"}]}
        extractor._answers_path.write_text(json.dumps(data))
        output = _OutputModel(units=[_UnitModel(unit_id="1")])
        extractor._output_path.write_text(output.model_dump_json(indent=2))
        result = await extractor._extract_units(_OutputModel)
        assert result == extractor._output_path

    def test_process_unit_raises_not_implemented(self, extractor) -> None:
        with pytest.raises(NotImplementedError):
            asyncio.run(BaseExtractor._process_unit(extractor, {"unit_id": "1"}))

    def test_a_subclass_must_name_its_output_file(self, tmp_path) -> None:
        """Otherwise the stage would silently write over answers.json."""
        with pytest.raises(ConfigurationError, match="OUTPUT_FILENAME"):
            BaseExtractor(extraction_paths(tmp_path))
