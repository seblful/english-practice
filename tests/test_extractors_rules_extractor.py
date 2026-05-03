"""Tests for RulesExtractor."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.english_practice.extractors.rules_extractor import RulesExtractor
from src.english_practice.models.agents import ExerciseRulesOutput, QuestionRuleItem
from src.english_practice.models.extraction import ExtractedFullRules


@pytest.fixture
def extractor(tmp_path) -> RulesExtractor:
    output_path = tmp_path / "output.json"
    answers_path = tmp_path / "answers.json"
    answers_full_path = tmp_path / "answers_full.json"
    exercises_dir = tmp_path / "exercises"
    content_dir = tmp_path / "content"
    grammar_md_dir = tmp_path / "grammar"
    exercises_dir.mkdir(parents=True)
    content_dir.mkdir(parents=True)
    grammar_md_dir.mkdir(parents=True)

    # Write source answers data
    answers_path.write_text(json.dumps({
        "units": [{
            "unit_id": "1",
            "exercises": [{
                "exercise_id": "1.1",
                "questions": [{"question_id": "1"}],
            }],
        }],
    }))

    # Write answers_full
    answers_full_path.write_text(json.dumps({
        "units": [{
            "unit_id": "1",
            "exercises": [{
                "exercise_id": "1.1",
                "questions": [{"question_id": "1", "is_open_ended": False}],
            }],
        }],
    }))

    return RulesExtractor(
        output_path, answers_path, exercises_dir, content_dir,
        answers_full_path, grammar_md_dir,
    )


class TestRulesExtractor:
    """Tests for RulesExtractor."""

    def test_get_grammar_md_finds_in_grammar_dir(self, extractor) -> None:
        path = extractor._grammar_md_dir / "1.md"
        path.write_text("# Grammar rule")
        assert extractor._get_grammar_md(1) == "# Grammar rule"

    def test_get_grammar_md_finds_in_content_dir(self, extractor) -> None:
        path = extractor._content_dir / "grammar" / "1.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Content rule")
        assert extractor._get_grammar_md(1) == "# Content rule"

    def test_get_grammar_md_not_found(self, extractor) -> None:
        assert extractor._get_grammar_md(999) is None

    def test_load_answers_full_data_returns_empty_if_missing(self, extractor) -> None:
        extractor._answers_full_path.unlink()
        assert extractor._load_answers_full_data() == {}

    def test_load_answers_full_data_loads(self, extractor) -> None:
        data = extractor._load_answers_full_data()
        assert "units" in data

    def test_build_answers_full_map(self, extractor) -> None:
        data = {
            "units": [{
                "exercises": [{
                    "exercise_id": "1.1",
                    "questions": [{"question_id": "1", "is_open_ended": False}],
                }],
            }],
        }
        result = extractor._build_answers_full_map(data)
        assert "1.1:1" in result

    def test_prepare_questions_returns_list(self, extractor) -> None:
        exercise = {
            "exercise_id": "1.1",
            "questions": [{"question_id": "1"}],
        }
        questions = extractor._prepare_questions(exercise, {"1.1:1": {"is_open_ended": False, "answers": [{"short_answer": "yes", "full_answer": "Yes!"}]}})
        assert len(questions) == 1
        assert questions[0]["question_id"] == "1"
        assert questions[0]["short_answers"] == ["yes"]

    def test_prepare_questions_empty_answers(self, extractor) -> None:
        exercise = {
            "exercise_id": "1.1",
            "questions": [{"question_id": "1"}],
        }
        questions = extractor._prepare_questions(exercise, {})
        assert len(questions) == 1
        assert questions[0]["short_answers"] == []

    def test_build_exercise_data(self, extractor) -> None:
        result = MagicMock()
        result.questions = [MagicMock(question_id="1", section_letter="A", rule="rule")]
        built = extractor._build_exercise_data("1.1", [{"question_id": "1"}], result)
        assert built.exercise_id == "1.1"
        assert built.questions[0].rule == "rule"

    @pytest.mark.asyncio
    async def test_process_unit(self, extractor) -> None:
        from english_practice.models.extraction import ExtractedExerciseRules
        with patch.object(extractor, "_get_grammar_md", return_value="# Grammar"):
            with patch.object(extractor, "_process_exercise") as mock_proc:
                mock_proc.return_value = ExtractedExerciseRules(
                    exercise_id="1.1", questions=[]
                )
                result = await extractor._process_unit(
                    {"unit_id": "1", "exercises": [{"exercise_id": "1.1"}]},
                    {},
                )
                assert result.unit_id == "1"

    @pytest.mark.asyncio
    async def test_process_exercise(self, extractor) -> None:
        exercise = {"exercise_id": "1.1", "questions": [{"question_id": "1"}]}
        expected = ExerciseRulesOutput(questions=[QuestionRuleItem(question_id="1")])

        with patch.object(extractor, "_get_image_path", return_value=Path("/fake/1.1.png")):
            with patch.object(extractor._extractor_agent, "extract_exercise", new=AsyncMock(return_value=expected)):
                result = await extractor._process_exercise(exercise, {}, "# md", "Test")
                assert result.exercise_id == "1.1"

    @pytest.mark.asyncio
    async def test_extract(self, extractor) -> None:
        with patch.object(extractor, "_load_answers_data", return_value={"units": []}):
            with patch.object(extractor, "_load_output", return_value=ExtractedFullRules()):
                with patch.object(extractor, "_save_output"):
                    result = await extractor.extract()
                    assert "output_path" in result
