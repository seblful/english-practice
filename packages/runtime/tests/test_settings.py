"""Tests for the settings both programs read."""

import os
from pathlib import Path

import pytest
from practice_core.providers import Provider
from pydantic import SecretStr

from practice_runtime.settings import (
    DATABASE_FILENAME,
    LAYOUT,
    RENAMED,
    BaseAppSettings,
    GeminiSettings,
    LangSmithSettings,
    LLMAppSettings,
    LLMSettings,
    OpenRouterSettings,
    PathSettings,
    env_var,
    load_env,
    load_settings,
    project_root,
    renamed_variables,
    secret_value,
    settings_env_vars,
)


def _configured(**overrides: object) -> LLMAppSettings:
    """Settings with a provider key in place, which is all they require."""
    fields: dict[str, object] = {
        "llm": LLMSettings(provider=Provider.GEMINI),
        "gemini": GeminiSettings(api_key=SecretStr("key")),
    }
    fields.update(overrides)
    return LLMAppSettings.model_validate(fields)


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
        monkeypatch.setenv("APP_PROJECT_ROOT", str(tmp_path))
        project_root.cache_clear()

        assert project_root() == tmp_path.resolve()

    def test_falls_back_to_the_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An installed copy with no repository around it still has to resolve."""
        monkeypatch.delenv("APP_PROJECT_ROOT", raising=False)
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
        (tmp_path / ".env").write_text("APP_ENVIRONMENT=staging\n", encoding="utf-8")
        monkeypatch.setattr("practice_runtime.settings.BASE_DIR", tmp_path)
        monkeypatch.delenv("APP_ENVIRONMENT", raising=False)

        assert load_settings(BaseAppSettings).app.environment == "staging"


class TestProviders:
    """Keys live once per provider, whatever calls it."""

    @pytest.mark.parametrize(
        ("provider", "expected"),
        [(Provider.GEMINI, "gem-key"), (Provider.OPENROUTER, "or-key")],
    )
    def test_credentials_follow_the_provider(
        self, provider: Provider, expected: str
    ) -> None:
        settings = BaseAppSettings(
            gemini=GeminiSettings(api_key=SecretStr("gem-key")),
            openrouter=OpenRouterSettings(api_key=SecretStr("or-key")),
        )

        assert settings.credentials(provider).key == expected

    @pytest.mark.parametrize("provider", list(Provider))
    def test_the_key_variable_matches_the_core_name(self, provider: Provider) -> None:
        """The app and the docs name the variable the settings actually read."""
        settings = BaseAppSettings()

        assert settings.credentials(provider).key_variable == provider.key_variable

    def test_reads_a_key_and_proxy_from_the_provider_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", " g \n")
        monkeypatch.setenv("OPENROUTER_PROXY", "socks5://localhost:9050")

        settings = BaseAppSettings()

        assert settings.gemini.key == "g"
        assert settings.openrouter.proxy == "socks5://localhost:9050"

    def test_the_chat_model_uses_its_providers_credentials(self) -> None:
        settings = _configured(llm=LLMSettings(provider=Provider.OPENROUTER))

        assert settings.llm_credentials is settings.openrouter

    def test_an_empty_variable_is_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A copied .env.example leaves GEMINI_PROXY= and friends empty."""
        monkeypatch.setenv("GEMINI_PROXY", "")
        monkeypatch.setenv("LLM_MODEL", "")
        monkeypatch.setenv("APP_ENVIRONMENT", "")

        settings = LLMAppSettings()

        assert settings.gemini.proxy is None
        assert settings.llm.model is None
        assert settings.app.environment == "development"

    def test_a_blank_key_is_unset(self) -> None:
        assert GeminiSettings(api_key=SecretStr("  ")).key is None


class TestLLMSettings:
    def test_gemini_is_the_default_provider(self) -> None:
        assert LLMSettings().provider is Provider.GEMINI

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            (Provider.GEMINI, "gemini-2.5-flash-lite"),
            (Provider.OPENROUTER, "google/gemma-4-26b-a4b-it"),
        ],
    )
    def test_an_unset_model_is_the_providers_default(
        self, provider: Provider, model: str
    ) -> None:
        assert LLMSettings(provider=provider, model="  ").active_model == model

    def test_a_named_model_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")

        settings = LLMSettings()

        assert settings.provider is Provider.OPENROUTER
        assert settings.active_model == "openai/gpt-4o-mini"


class TestMissingRequired:
    """The checks every program shares. Each adds its own on top."""

    def test_a_configured_provider_has_no_problems(self) -> None:
        assert _configured().missing_required() == []

    def test_reports_missing_provider_key(self) -> None:
        settings = _configured()
        settings.gemini.api_key = None

        assert settings.missing_required() == [
            "GEMINI_API_KEY is not set (LLM_PROVIDER=gemini)"
        ]

    def test_names_the_provider_that_needs_the_key(self) -> None:
        settings = _configured(llm=LLMSettings(provider=Provider.OPENROUTER))

        assert settings.missing_required() == [
            "OPENROUTER_API_KEY is not set (LLM_PROVIDER=openrouter)"
        ]

    def test_reports_missing_langsmith_key_only_when_tracing(self) -> None:
        settings = _configured()
        settings.langsmith = LangSmithSettings(tracing=True, api_key=None)

        assert any("LANGSMITH_API_KEY" in p for p in settings.missing_required())

    def test_an_untraced_run_needs_no_langsmith_key(self) -> None:
        settings = _configured()
        settings.langsmith = LangSmithSettings(tracing=False, api_key=None)

        assert settings.missing_required() == []

    def test_a_program_without_a_chat_model_needs_no_provider_key(self) -> None:
        """The bot grades through a decision model, so no LLM_PROVIDER key."""
        settings = BaseAppSettings()

        assert settings.missing_required() == []
        assert "llm" not in BaseAppSettings.model_fields

    def test_reports_everything_at_once(self) -> None:
        settings = _configured()
        settings.gemini.api_key = None
        settings.langsmith = LangSmithSettings(tracing=True, api_key=None)

        assert len(settings.missing_required()) == 2

    def test_a_renamed_variable_is_refused_with_its_new_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An old .env must not be half-read: say what each line became."""
        monkeypatch.setenv("DECISION_ROUTE", "openrouter")

        assert _configured().missing_required() == [
            "DECISION_ROUTE is no longer read: rename it to GRADER_PROVIDER"
        ]


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

    def test_the_unprefixed_database_path_is_no_longer_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_PATH", "legacy/place.db")

        assert PathSettings().database_path != Path("legacy/place.db")


class TestEnvVar:
    def test_is_the_group_prefix_plus_the_field(self) -> None:
        assert env_var(LLMSettings, "provider") == "LLM_PROVIDER"
        assert env_var(PathSettings(), "database_path") == "PATHS_DATABASE_PATH"

    @pytest.mark.parametrize("field", ["app", "logging", "paths", "langsmith"])
    def test_every_group_is_prefixed_with_its_own_name(self, field: str) -> None:
        """One rule for every variable: <GROUP>_<FIELD>, single underscores."""
        group = BaseAppSettings.model_fields[field].annotation

        assert isinstance(group, type)
        assert env_var(group, "") == f"{field.upper()}_"

    def test_every_variable_follows_the_rule(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name, value in {
            "APP_NAME": "x",
            "APP_ENVIRONMENT": "staging",
            "LOGGING_FILE_LEVEL": "DEBUG",
            "LOGGING_FILE": "elsewhere.log",
            "LLM_TEMPERATURE": "0.1",
        }.items():
            monkeypatch.setenv(name, value)

        settings = LLMAppSettings()

        assert settings.app.name == "x"
        assert settings.app.environment == "staging"
        assert settings.logging.file_level == "DEBUG"
        assert settings.logging.file == Path("elsewhere.log")
        assert settings.llm.temperature == 0.1


class TestRenamedVariables:
    def test_none_set_none_reported(self) -> None:
        assert renamed_variables() == []

    def test_a_removed_variable_is_told_to_go(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DASHSCOPE_API_KEY", "x")

        assert renamed_variables() == ["DASHSCOPE_API_KEY is no longer read: remove it"]

    def test_no_new_name_is_also_an_old_one(self) -> None:
        """A rename that points at another renamed variable would loop."""
        for new in filter(None, RENAMED.values()):
            assert not set(new.split(" or ")) & set(RENAMED)


class TestSettingsEnvVars:
    def test_finds_a_prefixed_group_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GEMINI_PROXY", "socks5://localhost:9050")

        assert "GEMINI_PROXY" in settings_env_vars(BaseAppSettings)

    def test_finds_a_subclass_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_MODEL", "m")

        assert "LLM_MODEL" in settings_env_vars(LLMAppSettings)
        assert "LLM_MODEL" not in settings_env_vars(BaseAppSettings)

    def test_finds_a_renamed_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests hide it too, or a developer's old .env would fail them."""
        monkeypatch.setenv("LOGGING__FILE_LEVEL", "DEBUG")

        assert "LOGGING__FILE_LEVEL" in settings_env_vars(BaseAppSettings)

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

    def test_every_declared_path_follows_the_data_dir(self, tmp_path: Path) -> None:
        """A path added to the model and forgotten in ``LAYOUT`` is stranded."""
        moved = PathSettings(data_dir=tmp_path)

        stranded = [
            name
            for name, value in vars(moved).items()
            if isinstance(value, Path) and not value.is_relative_to(tmp_path)
        ]

        assert stranded == []

    def test_the_layout_names_every_path_but_the_root(self) -> None:
        """``data_dir`` is the only path the layout does not derive."""
        declared = {name for name, _, _ in LAYOUT}
        fields = {
            name
            for name, info in PathSettings.model_fields.items()
            if info.annotation is Path
        }

        assert fields - declared == {"data_dir"}
        assert declared - fields == set()

    def test_the_layout_settles_each_parent_before_its_children(self) -> None:
        """Derivation reads the parent, so the order is the whole contract."""
        settled = {"data_dir"}
        for name, parent, _ in LAYOUT:
            assert parent in settled, f"{name} is derived from an unsettled {parent}"
            settled.add(name)

    def test_an_environment_variable_still_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PATHS_EXERCISES_DIR", str(tmp_path / "crops"))

        paths = PathSettings(data_dir=tmp_path)

        assert paths.exercises_dir == tmp_path / "crops"
