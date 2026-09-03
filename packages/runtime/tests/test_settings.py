"""Tests for the settings both programs read."""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from practice_runtime.settings import (
    DATABASE_FILENAME,
    BaseAppSettings,
    DashscopeSettings,
    GeminiSettings,
    LangSmithSettings,
    LLMProvider,
    LLMSettings,
    OpenRouterSettings,
    PathSettings,
    load_env,
    load_settings,
    project_root,
    secret_value,
    settings_env_vars,
)


def _configured(**overrides: object) -> BaseAppSettings:
    """Settings with a provider key in place, which is all the base requires."""
    fields: dict[str, object] = {
        "llm": LLMSettings(
            provider="dashscope",
            dashscope=DashscopeSettings(api_key=SecretStr("key")),
        )
    }
    fields.update(overrides)
    return BaseAppSettings.model_validate(fields)


def test_settings_load_from_env_file(tmp_env_file: Path) -> None:
    """Nested settings are populated from the env file and defaults."""
    settings = BaseAppSettings(_env_file=tmp_env_file)

    assert settings.app.environment == "test"
    assert settings.app.app_name == "english-practice"
    assert settings.logging.console_level == "INFO"


class TestSecretValue:
    def test_none_is_unset(self) -> None:
        assert secret_value(None) is None

    def test_blank_is_unset(self) -> None:
        assert secret_value(SecretStr("  ")) is None

    def test_returns_trimmed_text(self) -> None:
        assert secret_value(SecretStr(" token\n")) == "token"


class TestProjectRoot:
    def test_recognises_the_repository_by_what_is_in_it(self) -> None:
        """Counting parent directories breaks the moment a package moves."""
        root = project_root()

        assert (root / "packages").is_dir()
        assert (root / "pyproject.toml").is_file()

    def test_an_explicit_override_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP__PROJECT_ROOT", str(tmp_path))
        project_root.cache_clear()

        assert project_root() == tmp_path.resolve()

    def test_falls_back_to_the_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An installed copy with no repository around it still has to resolve."""
        monkeypatch.delenv("APP__PROJECT_ROOT", raising=False)
        monkeypatch.setattr(
            "practice_runtime.settings.Path.parents",
            property(lambda _: ()),
        )
        monkeypatch.chdir(tmp_path)
        project_root.cache_clear()

        assert project_root() == Path.cwd()

    def test_read_once_per_process(self) -> None:
        assert project_root() is project_root()


class TestLoadEnv:
    def test_environment_specific_file_wins_over_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("SHARED=base\nONLY_BASE=1\n", encoding="utf-8")
        (tmp_path / ".env.staging").write_text("SHARED=staging\n", encoding="utf-8")
        for name in ("SHARED", "ONLY_BASE"):
            monkeypatch.delenv(name, raising=False)

        applied = load_env(base_dir=tmp_path, environment="staging")

        assert applied["SHARED"] == "staging"
        assert applied["ONLY_BASE"] == "1"
        assert os.environ["SHARED"] == "staging"

    def test_real_environment_is_never_overwritten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A deployment's exported variable outranks a stale local file."""
        (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=stale\n", encoding="utf-8")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-deployment")

        applied = load_env(base_dir=tmp_path, environment="production")

        assert "TELEGRAM_BOT_TOKEN" not in applied
        assert os.environ["TELEGRAM_BOT_TOKEN"] == "from-deployment"

    def test_missing_files_are_ignored(self, tmp_path: Path) -> None:
        assert load_env(base_dir=tmp_path, environment="nope") == {}


class TestLoadSettings:
    def test_seeds_the_environment_before_reading_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The groups read os.environ, so the files have to land there first."""
        (tmp_path / ".env").write_text("APP__ENVIRONMENT=staging\n", encoding="utf-8")
        monkeypatch.setattr("practice_runtime.settings.BASE_DIR", tmp_path)
        monkeypatch.delenv("APP__ENVIRONMENT", raising=False)

        assert load_settings(BaseAppSettings).app.environment == "staging"


class TestActiveApiKey:
    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ("dashscope", "dash-key"),
            ("gemini", "gem-key"),
            ("openrouter", "or-key"),
        ],
        ids=["dashscope", "gemini", "openrouter"],
    )
    def test_returns_selected_provider_key(
        self, provider: LLMProvider, expected: str
    ) -> None:
        config = LLMSettings(
            provider=provider,
            dashscope=DashscopeSettings(api_key=SecretStr("dash-key")),
            gemini=GeminiSettings(api_key=SecretStr("gem-key")),
            openrouter=OpenRouterSettings(api_key=SecretStr("or-key")),
        )

        assert config.active_api_key == expected

    def test_none_when_selected_provider_has_no_key(self) -> None:
        assert LLMSettings(provider="gemini").active_api_key is None


class TestMissingRequired:
    """The checks every program shares. Each adds its own on top."""

    def test_a_configured_provider_has_no_problems(self) -> None:
        assert _configured().missing_required() == []

    def test_reports_missing_provider_key(self) -> None:
        settings = _configured()
        settings.llm.dashscope.api_key = None

        assert any("DASHSCOPE_API_KEY" in p for p in settings.missing_required())

    def test_names_the_provider_that_needs_the_key(self) -> None:
        settings = _configured(llm=LLMSettings(provider="openrouter"))

        assert any("OPENROUTER_API_KEY" in p for p in settings.missing_required())

    def test_reports_missing_langsmith_key_only_when_tracing(self) -> None:
        settings = _configured()
        settings.langsmith = LangSmithSettings(tracing=True, api_key=None)

        assert any("LANGSMITH_API_KEY" in p for p in settings.missing_required())

    def test_an_untraced_run_needs_no_langsmith_key(self) -> None:
        settings = _configured()
        settings.langsmith = LangSmithSettings(tracing=False, api_key=None)

        assert settings.missing_required() == []


class TestAppSettings:
    def test_a_deployment_wants_machine_readable_logs(self) -> None:
        assert _configured().app.is_production is False

    def test_production_is_recognised_by_name(self) -> None:
        settings = BaseAppSettings.model_validate(
            {"app": {"environment": "production"}}
        )

        assert settings.app.is_production is True


class TestPathSettings:
    def test_create_directories_skips_files(self, tmp_path: Path) -> None:
        paths = PathSettings(
            data_dir=tmp_path / "data",
            content_dir=tmp_path / "content",
            database_path=tmp_path / "content" / "app.db",
        )

        paths.create_directories()

        assert (tmp_path / "data").is_dir()
        assert not (tmp_path / "content" / "app.db").exists()

    def test_legacy_database_path_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The unprefixed DATABASE_PATH from older .env files still works."""
        monkeypatch.delenv("PATHS_DATABASE_PATH", raising=False)
        monkeypatch.setenv("DATABASE_PATH", "legacy/place.db")

        assert PathSettings().database_path == Path("legacy/place.db")


class TestSettingsEnvVars:
    def test_finds_a_prefixed_group_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GEMINI_PROXY", "socks5://localhost:9050")

        assert "GEMINI_PROXY" in settings_env_vars(BaseAppSettings)

    def test_finds_a_nested_plain_model_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`app` and `logging` are plain models, reached by the delimiter."""
        monkeypatch.setenv("LOGGING__FILE_LEVEL", "DEBUG")

        assert "LOGGING__FILE_LEVEL" in settings_env_vars(BaseAppSettings)

    def test_finds_a_legacy_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_PATH", "somewhere.db")

        assert "DATABASE_PATH" in settings_env_vars(BaseAppSettings)

    def test_ignores_everything_else(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOME_UNRELATED_VARIABLE", "1")

        assert "SOME_UNRELATED_VARIABLE" not in settings_env_vars(BaseAppSettings)


class TestRelocatingTheTree:
    """One field moves the layout; the rest follow it."""

    def test_setting_the_data_dir_moves_everything(self, tmp_path: Path) -> None:
        """This used to move one directory and leave nine behind."""
        paths = PathSettings(data_dir=tmp_path)

        assert paths.source_dir == tmp_path / "source"
        assert paths.content_dir == tmp_path / "content"
        assert paths.images_dir == tmp_path / "source" / "images"
        assert paths.grammar_pages_dir == tmp_path / "source" / "images" / "grammar"
        assert paths.exercises_dir == tmp_path / "content" / "exercises"
        assert paths.metadata_dir == tmp_path / "content" / "metadata"
        assert paths.database_path.parent == tmp_path / "content"

    def test_setting_the_content_dir_moves_what_sits_under_it(
        self, tmp_path: Path
    ) -> None:
        paths = PathSettings(content_dir=tmp_path / "elsewhere")

        assert paths.grammar_md_dir == tmp_path / "elsewhere" / "grammar"
        assert paths.exercises_dir == tmp_path / "elsewhere" / "exercises"
        assert paths.database_path == tmp_path / "elsewhere" / DATABASE_FILENAME

    def test_a_path_given_explicitly_is_left_alone(self, tmp_path: Path) -> None:
        elsewhere = tmp_path / "somewhere-else" / "db.sqlite"

        paths = PathSettings(data_dir=tmp_path, database_path=elsewhere)

        assert paths.database_path == elsewhere
        assert paths.content_dir == tmp_path / "content"

    def test_an_environment_variable_still_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PATHS_EXERCISES_DIR", str(tmp_path / "crops"))

        paths = PathSettings(data_dir=tmp_path)

        assert paths.exercises_dir == tmp_path / "crops"
