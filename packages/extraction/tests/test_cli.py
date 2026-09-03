"""Tests for the content pipeline CLI.

Each command is wiring: it reads the configured layout, builds one collaborator
and calls it. These tests assert the wiring, with the collaborators mocked --
the stages themselves are covered by their own tests.
"""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from practice_core.errors import ContentError
from practice_runtime.errors import ConfigurationError
from typer.testing import CliRunner

from practice_extraction import cli
from practice_extraction.bundle import BundleResult
from practice_extraction.constants import (
    END_ANSWER_PAGE,
    END_UNIT_PAGE,
    START_ANSWER_PAGE,
    START_UNIT_PAGE,
)
from practice_extraction.settings import Settings
from practice_extraction.stages import STAGE_BY_NAME
from tests.conftest import extraction_paths

runner = CliRunner()


@pytest.fixture
def staged(settings: Settings) -> Callable[[str], None]:
    """Return a helper that puts a stage's inputs in place.

    The CLI now refuses a stage whose inputs are absent, so a test that drives
    one has to say what it is standing on. That is the point of the check: a
    stage used to run happily on an empty tree.
    """

    def stage(name: str) -> None:
        for artifact in STAGE_BY_NAME[name].reads:
            path = artifact.path(settings)
            if path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            else:
                path.mkdir(parents=True, exist_ok=True)
                (path / "placeholder").write_text("x", encoding="utf-8")

    return stage


@pytest.fixture(autouse=True)
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Point the CLI at a temporary layout instead of the real ``data/``."""
    settings = Settings(paths=extraction_paths(tmp_path))
    settings.logging.log_file = tmp_path / "logs" / "app.log"
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


@pytest.fixture(autouse=True)
def _no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never build a real provider client: the stages here are mocked."""
    monkeypatch.setattr(cli, "get_llm", lambda _config: MagicMock())


def _invoke(*args: str) -> None:
    """Run one CLI command, failing the test if it exits non-zero."""
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == 0, result.output


def _awaitable(value: object):
    """Return a coroutine yielding ``value``, for ``asyncio.run`` to drive."""

    async def _coro() -> object:
        return value

    return _coro()


class TestCheck:
    """What a full run still needs, reported in one go."""

    def test_reports_what_is_missing(self, settings: Settings) -> None:
        result = runner.invoke(cli.app, ["check"])

        assert result.exit_code == 1
        assert "OCR_API_KEY" in result.output
        assert "source book" in result.output

    def test_succeeds_when_nothing_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, settings: Settings
    ) -> None:
        monkeypatch.setattr(type(settings), "missing_required", lambda _self: [])

        result = runner.invoke(cli.app, ["check"])

        assert result.exit_code == 0
        assert "looks good" in result.output


class TestCutPdf:
    """The book is cut into the sections the operator works from by hand."""

    @pytest.mark.parametrize(
        ("section", "pages"),
        [
            ("units", (START_UNIT_PAGE, END_UNIT_PAGE)),
            ("answers", (START_ANSWER_PAGE, END_ANSWER_PAGE)),
        ],
        ids=["units", "answers"],
    )
    def test_cuts_the_named_section(
        self,
        settings: Settings,
        staged: Callable[[str], None],
        section: str,
        pages: tuple[int, int],
    ) -> None:
        staged("cut-pdf")

        with patch.object(cli, "PDFHandler") as handler:
            _invoke("cut-pdf", section)

        call = handler.return_value.cut_pdf.call_args.kwargs
        assert (call["start_page"], call["end_page"]) == pages
        assert call["output_path"] == settings.paths.snippets_dir / f"{section}.pdf"

    def test_rejects_a_section_the_book_has_no_pages_for(self) -> None:
        result = runner.invoke(cli.app, ["cut-pdf", "index"])

        assert result.exit_code != 0


class TestSeparatePageImages:
    """Tests for splitting unit pages into grammar and exercise images."""

    def test_passes_the_unit_page_range_and_dpi(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("separate-page-images")

        with patch.object(cli, "PDFHandler") as handler:
            _invoke("separate-page-images")

        call = handler.return_value.separate_page_images.call_args.kwargs
        assert (call["start_page"], call["end_page"]) == (
            START_UNIT_PAGE,
            END_UNIT_PAGE,
        )
        assert call["dpi"] == settings.images.pages_dpi
        assert call["grammar_pages_dir"] == settings.paths.grammar_pages_dir


class TestOcrGrammarImages:
    """Tests for OCR-ing the grammar pages."""

    def test_reads_the_pages_and_writes_the_markdown(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("ocr-grammar-images")

        with patch.object(cli, "ImageOcrExtractor") as ocr:
            ocr.return_value.ocr_dir.return_value = [Path("1.md")]
            _invoke("ocr-grammar-images")

        assert ocr.call_args.kwargs["model"] == settings.ocr.model
        call = ocr.return_value.ocr_dir.call_args
        assert call.args[0] == settings.paths.grammar_pages_dir
        assert call.kwargs["output_dir"] == settings.paths.grammar_md_dir


class TestOrganizeExercises:
    """Tests for slicing page images into per-exercise images."""

    def test_reads_the_page_images_and_writes_the_exercises(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("organize-exercises")

        with patch.object(cli, "ExerciseOrganizer") as organizer:
            organizer.return_value.organize.return_value = [Path("1.1.png")]
            _invoke("organize-exercises")

        call = organizer.return_value.organize.call_args.kwargs
        assert call["file_path"] == settings.paths.exercises_pages_dir
        assert call["output_dir"] == settings.paths.exercises_dir


class TestLlmStages:
    """The two LLM stages take the layout and the run's one client."""

    def test_extract_answers_hands_over_the_paths(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("extract-answers")

        with patch.object(cli, "AnswersExtractor") as extractor:
            extractor.return_value.extract = MagicMock(
                return_value=_awaitable(Path("answers_full.json"))
            )
            _invoke("extract-answers")

        assert extractor.call_args.args[0] is settings.paths

    def test_extract_rules_hands_over_the_paths(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("extract-rules")

        with patch.object(cli, "RulesExtractor") as extractor:
            extractor.return_value.extract = MagicMock(
                return_value=_awaitable(Path("rules.json"))
            )
            _invoke("extract-rules")

        assert extractor.call_args.args[0] is settings.paths

    def test_the_two_stages_share_one_client(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        """A client owns a connection pool, and a run makes thousands of calls."""
        staged("extract-answers")

        with (
            patch.object(cli, "AnswersExtractor") as extractor,
            patch.object(cli, "AnswersAgent") as agent,
        ):
            extractor.return_value.extract = MagicMock(
                return_value=_awaitable(Path("answers_full.json"))
            )
            _invoke("extract-answers")

        assert agent.call_count == 1

    def test_a_provider_without_a_key_is_explained(
        self, monkeypatch: pytest.MonkeyPatch, staged: Callable[[str], None]
    ) -> None:
        staged("extract-answers")

        def explode(_config: object) -> None:
            raise ConfigurationError("DASHSCOPE_API_KEY is not set")

        monkeypatch.setattr(cli, "get_llm", explode)

        result = runner.invoke(cli.app, ["extract-answers"])

        assert result.exit_code == 1
        assert "DASHSCOPE_API_KEY is not set" in result.output


class TestPopulate:
    """The stage that writes the database the front ends read."""

    def test_hands_over_the_configured_layout(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("populate")

        with patch.object(cli.populate_module, "main", return_value=0) as main:
            _invoke("populate")

        assert main.call_args.kwargs == {"force": False, "paths": settings.paths}

    def test_passes_force_through(self, staged: Callable[[str], None]) -> None:
        staged("populate")

        with patch.object(cli.populate_module, "main", return_value=0) as main:
            _invoke("populate", "--force")

        assert main.call_args.kwargs["force"] is True

    def test_a_failed_import_is_the_command_exit_code(self) -> None:
        with patch.object(cli.populate_module, "main", return_value=1):
            result = runner.invoke(cli.app, ["populate"])

        assert result.exit_code == 1


class TestValidate:
    """The report on what is wrong with the database."""

    def test_checks_the_configured_database(
        self, settings: Settings, staged: Callable[[str], None]
    ) -> None:
        staged("validate")

        with patch.object(cli.validate_module, "main", return_value=0) as main:
            _invoke("validate")

        assert main.call_args.args[0] == settings.paths.database_path

    def test_errors_in_the_database_fail_the_command(
        self, staged: Callable[[str], None]
    ) -> None:
        staged("validate")

        with patch.object(cli.validate_module, "main", return_value=1):
            result = runner.invoke(cli.app, ["validate"])

        assert result.exit_code == 1


class TestBundle:
    """The compact copy of the database that ships inside the APK."""

    def test_reports_the_file_it_wrote_and_what_it_saved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        built: dict[str, object] = {}

        def fake_build(
            source: Path,
            target: Path,
            *,
            progress: Callable[[str], None] | None = None,
        ) -> BundleResult:
            built.update(source=source, target=target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"bundle")
            if progress is not None:
                progress("  units: 1 rows")
            return BundleResult(
                path=target, images=3, source_bytes=1000, bundled_bytes=100
            )

        monkeypatch.setattr(cli, "build_mobile_content", fake_build)
        source = tmp_path / "source.db"
        source.write_bytes(b"")
        output = tmp_path / "content.db"

        result = runner.invoke(
            cli.app,
            ["bundle", "--source", str(source), "--output", str(output)],
        )

        assert result.exit_code == 0
        assert built["source"] == source
        assert built["target"] == output
        assert "units: 1 rows" in result.output
        assert "3 images" in result.output

    def test_defaults_to_the_configured_database(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Path] = {}

        def fake_build(source: Path, target: Path, **_: object) -> BundleResult:
            seen["source"] = source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"bundle")
            return BundleResult(path=target, images=0, source_bytes=0, bundled_bytes=0)

        monkeypatch.setattr(cli, "build_mobile_content", fake_build)

        _invoke("bundle", "--output", str(settings.paths.content_dir / "out.db"))

        assert seen["source"] == settings.paths.database_path

    def test_a_missing_source_is_explained(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(*_args: object, **_kwargs: object) -> BundleResult:
            raise ContentError("No exercise database at nowhere.db.")

        monkeypatch.setattr(cli, "build_mobile_content", explode)

        result = runner.invoke(
            cli.app, ["bundle", "--output", str(tmp_path / "out.db")]
        )

        assert result.exit_code == 1
        assert "No exercise database" in result.output

    def test_writes_inside_the_app_package_by_default(self) -> None:
        """The app reads this file out of its own package, by this name."""
        default = cli.MOBILE_CONTENT_PATH

        assert default.name == "english_practice.db"
        assert default.parent.name == "content"
        assert default.parent.parent.name == "practice_app"


class TestTheStageGate:
    """A stage refuses to run on inputs that are not there.

    `extract-rules` run early used to return an empty mapping, send 566
    exercises to the model with no answers in the prompt, and cache every
    ruined unit so a re-run skipped them.
    """

    def test_a_stage_without_its_inputs_exits_non_zero(self) -> None:
        result = runner.invoke(cli.app, ["extract-rules"])

        assert result.exit_code == 1
        assert "extract-rules cannot run yet" in result.output

    def test_it_says_which_stage_would_produce_what_is_missing(self) -> None:
        result = runner.invoke(cli.app, ["extract-rules"])

        assert "run: practice-content extract-answers" in result.output

    def test_a_refused_stage_builds_no_client_and_spends_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The useful moment to stop is before the first paid call."""
        built = MagicMock()
        monkeypatch.setattr(cli, "get_llm", built)

        with patch.object(cli, "RulesExtractor") as extractor:
            result = runner.invoke(cli.app, ["extract-rules"])

        assert result.exit_code == 1
        built.assert_not_called()
        extractor.assert_not_called()

    def test_a_staged_run_is_allowed_through(
        self, staged: Callable[[str], None]
    ) -> None:
        staged("populate")

        with patch.object(cli.populate_module, "main", return_value=0) as main:
            result = runner.invoke(cli.app, ["populate"])

        assert result.exit_code == 0
        main.assert_called_once()

    def test_check_reports_every_stage(self) -> None:
        result = runner.invoke(cli.app, ["check"])

        for stage_name in ("cut-pdf", "extract-rules", "populate", "bundle"):
            assert stage_name in result.output

    def test_check_marks_a_finished_stage_done_and_the_next_one_ready(
        self, staged: Callable[[str], None]
    ) -> None:
        staged("populate")

        result = runner.invoke(cli.app, ["check"])

        # Everything populate reads is in place, so the stages that write those
        # artifacts are done and populate itself is ready to run.
        assert "extract-rules: done" in result.output
        assert "populate: ready" in result.output

    def test_a_failed_populate_fails_the_command(
        self, staged: Callable[[str], None]
    ) -> None:
        staged("populate")

        with patch.object(cli.populate_module, "main", return_value=1):
            result = runner.invoke(cli.app, ["populate"])

        assert result.exit_code == 1
