"""Tests for AnswersExtractor."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.english_practice.extractors.answers_extractor import AnswersExtractor
from src.english_practice.models.agents import ExerciseAnswersOutput, QuestionAnswerItem
from src.english_practice.models.extraction import ExtractedFullAnswers


@pytest.fixture
def extractor(tmp_path) -> AnswersExtractor:
    output_path = tmp_path / "output.json"
    answers_path = tmp_path / "answers_source.json"
    exercises_dir = tmp_path / "exercises"
    content_dir = tmp_path / "content"
    exercises_dir.mkdir(parents=True)
    content_dir.mkdir(parents=True)

    # Write source answers data
    answers_path.write_text(json.dumps({
        "units": [{
            "unit_id": "1",
            "exercises": [{
                "exercise_id": "1.1",
                "questions": [{"question_id": "1", "answer": "yes"}],
            }],
        }],
    }))

    return AnswersExtractor(output_path, answers_path, exercises_dir, content_dir)


class TestAnswersExtractor:
    """Tests for AnswersExtractor."""

    @pytest.mark.asyncio
    async def test_process_unit_returns_extracted_unit(self, extractor) -> None:
        unit = {
            "unit_id": "1",
            "exercises": [{
                "exercise_id": "1.1",
                "questions": [{"question_id": "1", "answer": "yes"}],
            }],
        }

        from english_practice.models.extraction import ExtractedExerciseAnswers
        with patch.object(extractor, "_process_exercise") as mock_process:
            mock_process.return_value = ExtractedExerciseAnswers(
                exercise_id="1.1", questions=[]
            )
            result = await extractor._process_unit(unit)
            assert result.unit_id == "1"
            assert len(result.exercises) == 1

    @pytest.mark.asyncio
    async def test_process_exercise_returns_extracted_exercise(self, extractor) -> None:
        exercise = {
            "exercise_id": "1.1",
            "questions": [{"question_id": "1", "answer": "yes"}],
        }
        expected_result = ExerciseAnswersOutput(
            questions=[QuestionAnswerItem(question_id="1", is_open_ended=False, short_answers=["yes"], full_answers=["Yes!"])]
        )

        with patch.object(extractor, "_get_image_path", return_value=Path("/fake/1.1.png")):
            with patch.object(extractor._extractor_agent, "extract_exercise", new=AsyncMock(return_value=expected_result)):
                result = await extractor._process_exercise(exercise, "Test Topic")
                assert result.exercise_id == "1.1"
                assert len(result.questions) == 1

    def test_build_exercise_data_open_ended(self, extractor) -> None:
        from src.english_practice.models.agents import QuestionAnswerItem
        result = MagicMock()
        result.questions = [QuestionAnswerItem(question_id="1", is_open_ended=True)]

        built = extractor._build_exercise_data("1.1", [{"question_id": "1", "short_answer": "yes"}], result)
        assert built.exercise_id == "1.1"
        assert built.questions[0].is_open_ended is True
        assert built.questions[0].answers == []

    def test_build_exercise_data_closed(self, extractor) -> None:
        result = MagicMock()
        q = MagicMock(
            question_id="1",
            is_open_ended=False,
            short_answers=["yes"],
            full_answers=["Yes!"],
        )
        result.questions = [q]

        built = extractor._build_exercise_data(
            "1.1",
            [{"question_id": "1", "short_answer": "yes"}],
            result,
        )
        assert built.exercise_id == "1.1"
        assert len(built.questions[0].answers) == 1

    def test_build_exercise_empty_full_answer_uses_fallback(self, extractor) -> None:
        result = MagicMock()
        q = MagicMock(
            question_id="1",
            is_open_ended=False,
            short_answers=["yes"],
            full_answers=[""],
        )
        result.questions = [q]

        built = extractor._build_exercise_data(
            "1.1",
            [{"question_id": "1", "short_answer": "yes"}],
            result,
        )
        assert built.questions[0].answers[0].full_answer == "[yes]"

    @pytest.mark.asyncio
    async def test_extract_calls_super(self, extractor) -> None:
        with patch.object(extractor, "_load_answers_data", return_value={"units": []}):
            with patch.object(extractor, "_load_output", return_value=ExtractedFullAnswers()):
                with patch.object(extractor, "_save_output"):
                    result = await extractor.extract()
                    assert "output_path" in result
