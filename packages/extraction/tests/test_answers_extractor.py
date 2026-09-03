"""Tests for AnswersExtractor."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from practice_extraction.agents import AnswersAgent
from practice_extraction.extractors.answers_extractor import AnswersExtractor
from practice_extraction.models import (
    AnswersQuestion,
    ExerciseAnswersOutput,
    ExtractedExerciseAnswers,
    ExtractedFullAnswers,
    QuestionAnswerItem,
)
from tests.conftest import extraction_paths


@pytest.fixture
def extractor(tmp_path) -> AnswersExtractor:
    paths = extraction_paths(tmp_path)

    # Write source answers data
    (paths.metadata_dir / "answers.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "1",
                        "exercises": [
                            {
                                "exercise_id": "1.1",
                                "questions": [{"question_id": "1", "answer": "yes"}],
                            }
                        ],
                    }
                ],
            }
        )
    )

    return AnswersExtractor(paths, AnswersAgent(MagicMock()))


class TestAnswersExtractor:
    """Tests for AnswersExtractor."""

    def test_takes_the_agent_it_is_given(self, tmp_path) -> None:
        """The seam that lets both stages share one chat-model client."""
        agent = AnswersAgent(MagicMock())

        extractor = AnswersExtractor(extraction_paths(tmp_path), agent)

        assert extractor._extractor_agent is agent

    def test_writes_beside_the_source_units(self, extractor) -> None:
        assert extractor._tree.output_path.name == "answers_full.json"
        assert (
            extractor._tree.output_path.parent == extractor._tree._answers_path.parent
        )

    @pytest.mark.asyncio
    async def test_process_unit_returns_extracted_unit(self, extractor) -> None:
        unit = {
            "unit_id": "1",
            "exercises": [
                {
                    "exercise_id": "1.1",
                    "questions": [{"question_id": "1", "answer": "yes"}],
                }
            ],
        }

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
            questions=[
                QuestionAnswerItem(
                    question_id="1",
                    is_open_ended=False,
                    short_answers=["yes"],
                    full_answers=["Yes!"],
                )
            ]
        )

        with (
            patch.object(
                extractor._tree, "image_path", return_value=Path("/fake/1.1.png")
            ),
            patch.object(
                extractor._extractor_agent,
                "extract_exercise",
                new=AsyncMock(return_value=expected_result),
            ),
        ):
            result = await extractor._process_exercise(exercise, "Test Topic")
            assert result.exercise_id == "1.1"
            assert len(result.questions) == 1

    def test_build_exercise_data_open_ended(self, extractor) -> None:

        result = MagicMock()
        result.questions = [QuestionAnswerItem(question_id="1", is_open_ended=True)]

        built = extractor._build_exercise_data(
            "1.1", [AnswersQuestion(question_id="1", short_answer="yes")], result
        )
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
            [AnswersQuestion(question_id="1", short_answer="yes")],
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
            [AnswersQuestion(question_id="1", short_answer="yes")],
            result,
        )
        assert built.questions[0].answers[0].full_answer == "[yes]"

    def test_question_missing_from_result_is_skipped(self, extractor) -> None:
        """A model that returns fewer questions must not abort the whole unit."""
        result = MagicMock()
        result.questions = [
            MagicMock(
                question_id="1",
                is_open_ended=False,
                short_answers=["yes"],
                full_answers=["Yes!"],
            )
        ]

        built = extractor._build_exercise_data(
            "1.1",
            [
                AnswersQuestion(question_id="1", short_answer="yes"),
                AnswersQuestion(question_id="2", short_answer="no"),
            ],
            result,
        )

        assert [q.question_id for q in built.questions] == ["1"]

    def test_short_answer_without_a_full_answer_is_kept(self, extractor) -> None:
        """Truncating here would silently drop an accepted answer."""
        result = MagicMock()
        result.questions = [
            MagicMock(
                question_id="1",
                is_open_ended=False,
                short_answers=["yes", "sure"],
                full_answers=["Yes!"],
            )
        ]

        built = extractor._build_exercise_data(
            "1.1", [AnswersQuestion(question_id="1", short_answer="yes")], result
        )

        answers = built.questions[0].answers
        assert [a.short_answer for a in answers] == ["yes", "sure"]
        assert [a.full_answer for a in answers] == ["Yes!", "[sure]"]

    @pytest.mark.asyncio
    async def test_extract_calls_super(self, extractor) -> None:
        with (
            patch.object(extractor._tree, "source_answers", return_value={"units": []}),
            patch.object(
                extractor._tree, "load_output", return_value=ExtractedFullAnswers()
            ),
            patch.object(extractor._tree, "save_output"),
        ):
            result = await extractor.extract()
            assert result == extractor._tree.output_path
