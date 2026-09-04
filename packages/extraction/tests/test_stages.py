"""Tests for the pipeline's declared stage order."""

from pathlib import Path

import pytest
from practice_runtime.errors import ConfigurationError
from practice_runtime.settings import PathSettings

from practice_extraction.settings import Settings
from practice_extraction.stages import (
    STAGE_BY_NAME,
    STAGES,
    Artifact,
    Stage,
    register,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings over an empty scratch layout."""
    return Settings(paths=PathSettings(data_dir=tmp_path))


class TestTheDeclaredOrder:
    def test_every_input_is_produced_before_it_is_needed(self) -> None:
        """The check that replaces the README's numbered list."""
        produced: set[str] = set()
        for stage in STAGES:
            for artifact in stage.reads:
                if artifact.produced_by is not None:
                    assert artifact.produced_by in produced, (
                        f"{stage.name} reads {artifact.name}, "
                        f"which {artifact.produced_by} has not run to write yet"
                    )
            produced.add(stage.name)

    def test_every_produced_artifact_names_a_real_stage(self) -> None:
        for stage in STAGES:
            for artifact in (*stage.reads, *stage.writes):
                if artifact.produced_by is not None:
                    assert artifact.produced_by in STAGE_BY_NAME

    def test_a_stage_does_not_claim_to_write_its_own_input(self) -> None:
        for stage in STAGES:
            assert not set(stage.reads) & set(stage.writes)

    def test_the_stages_are_addressable_by_name(self) -> None:
        assert set(STAGE_BY_NAME) == {stage.name for stage in STAGES}


class TestMissingInputs:
    def test_an_empty_tree_leaves_every_stage_waiting(self, settings: Settings) -> None:
        rules = STAGE_BY_NAME["extract-rules"]

        assert len(rules.missing_inputs(settings)) == len(rules.reads)

    def test_the_absence_names_the_stage_that_would_fix_it(
        self, settings: Settings
    ) -> None:
        """A missing input is actionable, or it says to bring it by hand."""
        missing = STAGE_BY_NAME["extract-rules"].missing_inputs(settings)

        assert any("run: practice-content extract-answers" in line for line in missing)
        assert any("supply it by hand" in line for line in missing)

    def test_a_staged_input_stops_being_missing(self, settings: Settings) -> None:
        populate = STAGE_BY_NAME["populate"]
        titles = next(a for a in populate.reads if "unit titles" in a.name)
        titles.path(settings).parent.mkdir(parents=True, exist_ok=True)
        titles.path(settings).write_text("{}", encoding="utf-8")

        missing = populate.missing_inputs(settings)

        assert not any("unit titles" in line for line in missing)


class TestArtifactPresence:
    def test_an_empty_directory_does_not_count_as_produced(
        self, settings: Settings
    ) -> None:
        """Every command creates the tree it writes into before it runs."""
        crops = Artifact("crops", lambda s: s.paths.exercises_dir)
        crops.path(settings).mkdir(parents=True, exist_ok=True)

        assert crops.exists(settings) is False

    def test_a_directory_with_something_in_it_counts(self, settings: Settings) -> None:
        crops = Artifact("crops", lambda s: s.paths.exercises_dir)
        crops.path(settings).mkdir(parents=True, exist_ok=True)
        (crops.path(settings) / "1.1.png").write_bytes(b"x")

        assert crops.exists(settings) is True

    def test_a_file_counts_once_it_is_written(self, settings: Settings) -> None:
        database = Artifact("db", lambda s: s.paths.database_path)
        database.path(settings).parent.mkdir(parents=True, exist_ok=True)

        assert database.exists(settings) is False

        database.path(settings).write_bytes(b"sqlite")

        assert database.exists(settings) is True


class TestIsDone:
    def test_a_stage_with_nothing_written_is_not_done(self, settings: Settings) -> None:
        assert STAGE_BY_NAME["populate"].is_done(settings) is False

    def test_a_stage_that_writes_nothing_is_trivially_done(
        self, settings: Settings
    ) -> None:
        assert Stage("report").is_done(settings) is True


class TestRunning:
    """A stage does something. The record used to declare only its files."""

    def test_a_stage_nothing_has_declared_says_so(self, settings: Settings) -> None:
        """Reached when the module holding the runner was never imported."""
        orphan = Stage("not-a-real-stage")

        with pytest.raises(ConfigurationError, match="no runner is declared"):
            orphan.run(settings)

    def test_the_runner_is_handed_the_settings(self, settings: Settings) -> None:
        seen: list[Settings] = []
        stage = Stage("scratch-stage")
        register(stage, seen.append)

        assert stage.run(settings) == 0
        assert seen == [settings]

    def test_the_runner_decides_the_exit_code(self, settings: Settings) -> None:
        stage = Stage("failing-stage")
        register(stage, lambda _settings: 3)

        assert stage.run(settings) == 3
