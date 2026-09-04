"""Tests for the content tree an extraction stage reads and writes."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from practice_extraction.extractors import unit_store
from practice_extraction.extractors.unit_store import UnitStore
from practice_extraction.models import ExtractedUnitsRoot
from tests.conftest import extraction_paths


class _QuestionModel(BaseModel):
    question_id: str


class _ExerciseModel(BaseModel):
    questions: list[_QuestionModel] = []


class _UnitModel(BaseModel):
    """A unit shaped like the two the extractors really build."""

    unit_id: str
    exercises: list[_ExerciseModel] = []


class _OutputModel(ExtractedUnitsRoot[_UnitModel]):
    """The file a stage writes."""


@pytest.fixture
def store(tmp_path: Path) -> UnitStore:
    """A store over a temporary content layout."""
    return UnitStore(extraction_paths(tmp_path), "output.json")


async def _one_unit(unit: dict) -> _UnitModel:
    """Process a unit the way a stage does, without an LLM."""
    return _UnitModel(unit_id=unit["unit_id"])


class TestTheTopicMap:
    def test_a_unit_is_filed_under_its_topic(self, tmp_path: Path) -> None:
        paths = extraction_paths(tmp_path)
        (paths.metadata_dir / "topic_to_unit.json").write_text(
            json.dumps([{"topic": "Present Tenses", "unit_ids": [1, 2]}])
        )

        store = UnitStore(paths, "output.json")

        assert store.topic_name("1") == "Present Tenses"
        assert store.topic_name("2") == "Present Tenses"

    def test_a_unit_the_map_does_not_list(self, store: UnitStore) -> None:
        assert store.topic_name("999") == "Unknown Topic"

    def test_no_map_at_all(self, store: UnitStore) -> None:
        assert store.topic_name("1") == "Unknown Topic"


class TestTheCrops:
    def test_finds_the_exercise_image(self, store: UnitStore, tmp_path: Path) -> None:
        img_path = extraction_paths(tmp_path).exercises_dir / "1" / "1.1.png"
        img_path.parent.mkdir(parents=True)
        img_path.write_text("img")

        assert store.image_path("1.1") == img_path

    def test_an_exercise_with_no_crop(self, store: UnitStore) -> None:
        assert store.image_path("99.99") is None

    def test_an_id_that_is_not_an_exercise(self, store: UnitStore) -> None:
        assert store.image_path("invalid") is None


class TestTheGrammarPages:
    def test_reads_the_page_for_a_unit(self, store: UnitStore, tmp_path: Path) -> None:
        page = extraction_paths(tmp_path).grammar_md_dir / "7.md"
        page.write_text("# Present Continuous", encoding="utf-8")

        assert store.grammar_markdown(7) == "# Present Continuous"

    def test_a_unit_never_read(self, store: UnitStore) -> None:
        assert store.grammar_markdown(7) is None


class TestTheAnswerKey:
    def test_a_missing_key_reads_as_empty(self, store: UnitStore) -> None:
        assert store.source_answers() == {}

    def test_the_key_is_decoded(self, store: UnitStore) -> None:
        data = {"units": [{"unit_id": "1"}]}
        store._answers_path.write_text(json.dumps(data))

        assert store.source_answers() == data


class TestResuming:
    def test_a_run_that_has_not_started(self, store: UnitStore) -> None:
        assert store.load_output(_OutputModel).units == []

    def test_a_run_that_was_interrupted(self, store: UnitStore) -> None:
        output = _OutputModel(units=[_UnitModel(unit_id="1")])
        store.output_path.write_text(output.model_dump_json(indent=2))

        loaded = store.load_output(_OutputModel)

        assert [unit.unit_id for unit in loaded.units] == ["1"]

    def test_saving_creates_the_file(self, store: UnitStore) -> None:
        store.save_output(_OutputModel(units=[_UnitModel(unit_id="1")]))

        assert store.output_path.exists()

    async def test_every_unit_is_processed(self, store: UnitStore) -> None:
        store._answers_path.write_text(
            json.dumps({"units": [{"unit_id": "1"}, {"unit_id": "2"}]})
        )

        result = await store.extract_units(_OutputModel, _one_unit)

        assert result == store.output_path
        assert [u.unit_id for u in store.load_output(_OutputModel).units] == ["1", "2"]

    async def test_a_unit_already_done_is_skipped(self, store: UnitStore) -> None:
        """This is what makes a run interrupted at unit 180 continue."""
        store._answers_path.write_text(json.dumps({"units": [{"unit_id": "1"}]}))
        done = _OutputModel(units=[_UnitModel(unit_id="1")])
        store.output_path.write_text(done.model_dump_json(indent=2))

        processed: list[str] = []

        async def record(unit: dict) -> _UnitModel:
            processed.append(unit["unit_id"])
            return _UnitModel(unit_id=unit["unit_id"])

        assert await store.extract_units(_OutputModel, record) == store.output_path
        assert processed == []


class TestHollowUnits:
    """A unit is cached by its presence, so an empty one must be visible."""

    @pytest.fixture
    def warnings(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
        """Collect what the store logs at WARNING."""
        collected: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            unit_store.logger,
            "warning",
            lambda event, **fields: collected.append((event, fields)),
        )
        return collected

    def test_a_unit_that_produced_questions_is_quiet(
        self, warnings: list[tuple[str, dict]]
    ) -> None:
        unit = _UnitModel(
            unit_id="7",
            exercises=[_ExerciseModel(questions=[_QuestionModel(question_id="1")])],
        )

        unit_store._warn_if_hollow("7", unit)

        assert warnings == []

    def test_a_unit_whose_exercises_are_all_empty_is_reported(
        self, warnings: list[tuple[str, dict]]
    ) -> None:
        unit = _UnitModel(unit_id="7", exercises=[_ExerciseModel()])

        unit_store._warn_if_hollow("7", unit)

        assert warnings == [("unit_extracted_empty", {"unit_id": "7", "exercises": 1})]

    async def test_the_warning_lands_during_a_run(
        self, store: UnitStore, warnings: list[tuple[str, dict]]
    ) -> None:
        store._answers_path.write_text(json.dumps({"units": [{"unit_id": "1"}]}))

        await store.extract_units(_OutputModel, _one_unit)

        assert ("unit_extracted_empty", {"unit_id": "1", "exercises": 0}) in warnings
