"""Tests for RulesExtractor."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from practice_extraction.agents import RulesAgent
from practice_extraction.extractors.answers_extractor import AnswersExtractor
from practice_extraction.extractors.rules_extractor import RulesExtractor
from practice_extraction.models import (
    ExerciseRulesOutput,
    ExtractedExerciseRules,
    ExtractedFullRules,
    ExtractedUnitRules,
    QuestionRuleItem,
    RulesQuestion,
)
from tests.conftest import extraction_paths


@pytest.fixture
def extractor(tmp_path) -> RulesExtractor:
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
                                "questions": [{"question_id": "1"}],
                            }
                        ],
                    }
                ],
            }
        )
    )

    # Write answers_full: the previous stage's output
    (paths.metadata_dir / "answers_full.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "1",
                        "exercises": [
                            {
                                "exercise_id": "1.1",
                                "questions": [
                                    {"question_id": "1", "is_open_ended": False}
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )

    return RulesExtractor(paths, RulesAgent(MagicMock()))


class TestRulesExtractor:
    """Tests for RulesExtractor."""

    def test_takes_the_agent_it_is_given(self, tmp_path) -> None:
        """The seam that lets both stages share one chat-model client."""
        agent = RulesAgent(MagicMock())

        extractor = RulesExtractor(extraction_paths(tmp_path), agent)

        assert extractor._extractor_agent is agent

    def test_reads_what_the_answers_stage_wrote(self, extractor) -> None:
        """The stage dependency is derived, not kept in step by the caller."""
        assert extractor._answers_full_path == (
            extractor._paths.metadata_dir / AnswersExtractor.OUTPUT_FILENAME
        )

    def test_get_grammar_md_reads_the_unit_file(self, extractor) -> None:
        path = extractor._paths.grammar_md_dir / "1.md"
        path.write_text("# Grammar rule")
        assert extractor._get_grammar_md(1) == "# Grammar rule"

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
            "units": [
                {
                    "exercises": [
                        {
                            "exercise_id": "1.1",
                            "questions": [{"question_id": "1", "is_open_ended": False}],
                        }
                    ],
                }
            ],
        }
        result = extractor._build_answers_full_map(data)
        assert ("1.1", "1") in result

    def test_prepare_questions_returns_list(self, extractor) -> None:
        exercise = {
            "exercise_id": "1.1",
            "questions": [{"question_id": "1"}],
        }
        extractor._answers_full_map = {
            ("1.1", "1"): {
                "is_open_ended": False,
                "answers": [{"short_answer": "yes", "full_answer": "Yes!"}],
            }
        }

        questions = extractor._prepare_questions(exercise)
        assert questions == [
            RulesQuestion(question_id="1", short_answers=["yes"], full_answers=["Yes!"])
        ]

    def test_prepare_questions_empty_answers(self, extractor) -> None:
        exercise = {
            "exercise_id": "1.1",
            "questions": [{"question_id": "1"}],
        }
        extractor._answers_full_map = {}

        questions = extractor._prepare_questions(exercise)
        assert questions == [RulesQuestion(question_id="1")]

    def test_build_exercise_data(self, extractor) -> None:
        result = MagicMock()
        result.questions = [MagicMock(question_id="1", section_letter="A", rule="rule")]
        built = extractor._build_exercise_data(
            "1.1", [RulesQuestion(question_id="1")], result
        )
        assert built.exercise_id == "1.1"
        assert built.questions[0].rule == "rule"

    def test_question_missing_from_result_is_skipped(self, extractor) -> None:
        """A model that returns fewer questions must not abort the whole unit."""
        result = MagicMock()
        result.questions = [MagicMock(question_id="1", section_letter="A", rule="rule")]

        built = extractor._build_exercise_data(
            "1.1",
            [RulesQuestion(question_id="1"), RulesQuestion(question_id="2")],
            result,
        )

        assert [q.question_id for q in built.questions] == ["1"]

    @pytest.mark.asyncio
    async def test_process_unit(self, extractor) -> None:

        with (
            patch.object(extractor, "_get_grammar_md", return_value="# Grammar"),
            patch.object(extractor, "_process_exercise") as mock_proc,
        ):
            mock_proc.return_value = ExtractedExerciseRules(
                exercise_id="1.1", questions=[]
            )
            result = await extractor._process_unit(
                {"unit_id": "1", "exercises": [{"exercise_id": "1.1"}]}
            )
            assert result.unit_id == "1"

    @pytest.mark.asyncio
    async def test_process_exercise(self, extractor) -> None:
        exercise = {"exercise_id": "1.1", "questions": [{"question_id": "1"}]}
        expected = ExerciseRulesOutput(questions=[QuestionRuleItem(question_id="1")])

        with (
            patch.object(
                extractor, "_get_image_path", return_value=Path("/fake/1.1.png")
            ),
            patch.object(
                extractor._extractor_agent,
                "extract_exercise",
                new=AsyncMock(return_value=expected),
            ),
        ):
            result = await extractor._process_exercise(exercise, "# md", "Test")
            assert result.exercise_id == "1.1"

    @pytest.mark.asyncio
    async def test_process_unit_without_grammar_markdown(self, extractor) -> None:
        """A missing unit file must not stop the run; the prompt gets no rules."""
        with (
            patch.object(extractor, "_get_grammar_md", return_value=None),
            patch.object(extractor, "_process_exercise") as mock_proc,
        ):
            mock_proc.return_value = ExtractedExerciseRules(
                exercise_id="1.1", questions=[]
            )

            result = await extractor._process_unit(
                {"unit_id": "1", "exercises": [{"exercise_id": "1.1"}]}
            )

            assert result.unit_id == "1"
            call = mock_proc.await_args
            assert call is not None
            assert call.args[1] == ""

    @pytest.mark.asyncio
    async def test_extract(self, extractor) -> None:
        with (
            patch.object(extractor, "_load_answers_data", return_value={"units": []}),
            patch.object(extractor, "_load_output", return_value=ExtractedFullRules()),
            patch.object(extractor, "_save_output"),
        ):
            result = await extractor.extract()
            assert result == extractor._output_path

    @pytest.mark.asyncio
    async def test_extract_processes_and_saves_each_unit(self, extractor) -> None:
        output = ExtractedFullRules()
        unit = ExtractedUnitRules(unit_id="1", exercises=[])

        with (
            patch.object(extractor, "_load_output", return_value=output),
            patch.object(extractor, "_process_unit", return_value=unit),
            patch.object(extractor, "_save_output") as mock_save,
        ):
            await extractor.extract()

            assert [u.unit_id for u in output.units] == ["1"]
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_resumes_past_processed_units(self, extractor) -> None:
        """Re-running must not redo the units already written out."""
        output = ExtractedFullRules(units=[ExtractedUnitRules(unit_id="1")])

        with (
            patch.object(extractor, "_load_output", return_value=output),
            patch.object(extractor, "_process_unit") as mock_process,
            patch.object(extractor, "_save_output") as mock_save,
        ):
            await extractor.extract()

            mock_process.assert_not_called()
            mock_save.assert_not_called()
