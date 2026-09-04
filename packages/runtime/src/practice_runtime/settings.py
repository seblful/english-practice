"""The settings both programs read.

Every setting is resolved from the environment through pydantic-settings, so the
process environment is the single source of truth. Files only seed it: values
already exported by the shell, Docker, or CI always win over a checked-out
``.env`` (see :func:`load_env`).

What is here is what the bot and the content pipeline both need — where the
data lives, how to log, which LLM to call, whether to trace. What only one of
them needs stays with it: the bot owns its Telegram groups, the pipeline owns
its book, OCR and page-rendering groups, and each composes a root model from
:class:`BaseAppSettings` plus its own. That split is the reason the bot's
container no longer needs an OCR key to start.

Settings are read through each program's own ``get_settings()``, which caches
one instance for the process. Importing this module reads nothing.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, assert_never

from dotenv import dotenv_values
from pydantic import AliasChoices, BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BASE_DIR",
    "LAYOUT",
    "AppSettings",
    "BaseAppSettings",
    "DashscopeSettings",
    "GeminiSettings",
    "LLMProvider",
    "LLMSettings",
    "LangSmithSettings",
    "LogLevel",
    "LoggingSettings",
    "OpenRouterSettings",
    "PathSettings",
    "load_env",
    "load_settings",
    "project_root",
    "secret_value",
    "settings_env_vars",
]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMProvider = Literal["dashscope", "gemini", "openrouter"]

# Chosen by an OS variable; a missing .env.<environment> is ignored.
_ENVIRONMENT_VAR = "APP__ENVIRONMENT"
_DEFAULT_ENVIRONMENT = "development"
_ROOT_VAR = "APP__PROJECT_ROOT"


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Return the repository root: the directory holding ``data/`` and ``.env``.

    This package is one of several under ``packages/``, and it is installed
    into a virtual environment rather than imported from its source tree, so
    counting parent directories off ``__file__`` — which is what this used to
    do — would point somewhere different depending on how it was installed.
    Instead the root is recognised by what is in it, which is the same whether
    the package is editable, installed, or inside a container.

    Returns:
        The repository root; the working directory when nothing looks like one,
        which is the case for an installed copy with no repository around it.
        ``$APP__PROJECT_ROOT`` overrides both.
    """
    override = os.getenv(_ROOT_VAR)
    if override:
        return Path(override).expanduser().resolve()

    for directory in Path(__file__).resolve().parents:
        if (directory / "pyproject.toml").is_file() and (
            directory / "packages"
        ).is_dir():
            return directory

    return Path.cwd()


BASE_DIR = project_root()

#: The database every front end opens, inside whatever content tree is set.
DATABASE_FILENAME = "english_practice.db"

#: What a path field holds until the layout below fills it in.
_DERIVED = Path()

#: The tree, declared once: field, parent, name. Order is dependency order.
LAYOUT: tuple[tuple[str, str, str], ...] = (
    ("source_dir", "data_dir", "source"),
    ("content_dir", "data_dir", "content"),
    ("snippets_dir", "source_dir", "snippets"),
    ("images_dir", "source_dir", "images"),
    ("grammar_pages_dir", "images_dir", "grammar"),
    ("exercises_pages_dir", "images_dir", "exercises"),
    ("grammar_md_dir", "content_dir", "grammar"),
    ("exercises_dir", "content_dir", "exercises"),
    ("metadata_dir", "content_dir", "metadata"),
    ("database_path", "content_dir", DATABASE_FILENAME),
)


def secret_value(secret: SecretStr | None) -> str | None:
    """Return the plain text behind an optional secret.

    Args:
        secret: The secret to unwrap, if one is configured.

    Returns:
        The secret's text, or ``None`` when it is unset or blank. Blank counts
        as unset so that ``KEY=`` in an env file does not read as configured.
    """
    if secret is None:
        return None
    return secret.get_secret_value().strip() or None


def load_env(
    base_dir: Path | None = None,
    environment: str | None = None,
) -> dict[str, str]:
    """Seed ``os.environ`` from ``.env`` and ``.env.{environment}``.

    The nested settings groups below are each ``BaseSettings`` in their own
    right and resolve flat variables such as ``TELEGRAM_BOT_TOKEN`` from the
    process environment, so env files have to be materialised there before any
    group is constructed.

    Precedence, highest first: the real process environment, then
    ``.env.{environment}``, then ``.env``. Variables that are already exported
    are never overwritten — a deployment that passes ``TELEGRAM_BOT_TOKEN`` in
    the environment must not be silently downgraded to a stale local file.

    Args:
        base_dir: Directory holding the env files. Defaults to the repo root.
        environment: Environment name selecting ``.env.{environment}``.
            Defaults to ``$APP__ENVIRONMENT``, or ``development``.

    Returns:
        The variables this call actually set, for logging and tests.
    """
    root = base_dir or BASE_DIR
    env_name = environment or os.getenv(_ENVIRONMENT_VAR, _DEFAULT_ENVIRONMENT)

    # Later files win, so the environment-specific file overrides the base.
    from_files: dict[str, str] = {}
    for env_file in (root / ".env", root / f".env.{env_name}"):
        if not env_file.exists():
            continue
        from_files.update(
            {
                key: value
                for key, value in dotenv_values(env_file, encoding="utf-8").items()
                if value is not None
            }
        )

    applied = {k: v for k, v in from_files.items() if k not in os.environ}
    os.environ.update(applied)
    return applied


class AppSettings(BaseModel):
    """Application identity and environment."""

    app_name: str = Field(default="english-practice", description="Application name")
    environment: str = Field(
        default=_DEFAULT_ENVIRONMENT, description="Environment name"
    )

    @property
    def is_production(self) -> bool:
        """Whether this process is running a deployment rather than a laptop."""
        return self.environment == "production"


class LoggingSettings(BaseModel):
    """Logging destinations and verbosity."""

    file_level: LogLevel = Field(default="INFO", description="File log level")
    console_level: LogLevel = Field(default="INFO", description="Console log level")
    log_file: Path = Field(default=Path("logs/app.log"), description="Log file path")


class PathSettings(BaseSettings):
    """Filesystem layout for source material, generated content, and the database.

    Both programs read this group: the pipeline writes the whole tree, and the
    bot opens the one file at the end of it.
    """

    # populate_by_name lets callers pass `database_path=` an alias would shadow.
    model_config = SettingsConfigDict(
        env_prefix="PATHS_", case_sensitive=False, populate_by_name=True
    )

    data_dir: Path = BASE_DIR / "data"
    source_dir: Path = _DERIVED
    content_dir: Path = _DERIVED
    snippets_dir: Path = _DERIVED
    images_dir: Path = _DERIVED
    grammar_pages_dir: Path = _DERIVED
    exercises_pages_dir: Path = _DERIVED
    grammar_md_dir: Path = _DERIVED
    exercises_dir: Path = _DERIVED
    metadata_dir: Path = _DERIVED

    # DATABASE_PATH is accepted as a legacy alias: the group was unprefixed.
    database_path: Path = Field(
        default=_DERIVED,
        validation_alias=AliasChoices("PATHS_DATABASE_PATH", "DATABASE_PATH"),
        description="SQLite database file",
    )

    @model_validator(mode="after")
    def _derive_unset_paths(self) -> "PathSettings":
        """Build every path the caller did not set from the one above it.

        A field the caller or the environment set is left exactly as given.

        Returns:
            The settings, with the rest of the tree hung off ``data_dir``.
        """
        for name, parent, segment in LAYOUT:
            if name not in self.model_fields_set:
                setattr(self, name, getattr(self, parent) / segment)
        return self

    def create_directories(self) -> None:
        """Create every configured directory.

        Only the extraction pipeline needs the source and content tree to
        exist, so this is called explicitly by that entry point rather than on
        import.
        """
        for path in self.model_dump().values():
            if (
                isinstance(path, Path)
                and not path.suffix  # Skip files (paths with extensions)
            ):
                path.mkdir(parents=True, exist_ok=True)


class DashscopeSettings(BaseSettings):
    """DashScope (Alibaba) OpenAI-compatible endpoint."""

    model_config = SettingsConfigDict(env_prefix="DASHSCOPE_", case_sensitive=False)

    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    api_key: SecretStr | None = None
    model: str = "qwen3-vl-flash-2026-01-22"
    temperature: float = 0.7
    max_tokens: int = 2048


class GeminiSettings(BaseSettings):
    """Google Gemini API settings."""

    model_config = SettingsConfigDict(env_prefix="GEMINI_", case_sensitive=False)

    api_key: SecretStr | None = None
    model: str = "gemini-2.5-flash-lite"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    proxy: str | None = None


class OpenRouterSettings(BaseSettings):
    """OpenRouter API settings."""

    model_config = SettingsConfigDict(env_prefix="OPENROUTER_", case_sensitive=False)

    api_key: SecretStr | None = None
    model: str = "google/gemma-4-26b-a4b-it"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMSettings(BaseSettings):
    """Which LLM provider to use, and each provider's configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_", case_sensitive=False)

    provider: LLMProvider = "dashscope"
    request_timeout: float = Field(
        default=60.0, gt=0, description="Per-request timeout in seconds"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Retries for transient provider failures"
    )
    dashscope: DashscopeSettings = Field(default_factory=DashscopeSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)

    @property
    def active_api_key(self) -> str | None:
        """Return the API key of the selected provider, if configured."""
        match self.provider:
            case "dashscope":
                provider_settings = self.dashscope
            case "gemini":
                provider_settings = self.gemini
            case "openrouter":
                provider_settings = self.openrouter
            case unreachable:  # pragma: no cover - the Literal is validated upstream
                assert_never(unreachable)
        return secret_value(provider_settings.api_key)


class LangSmithSettings(BaseSettings):
    """LangSmith tracing settings."""

    model_config = SettingsConfigDict(env_prefix="LANGSMITH_", case_sensitive=False)

    api_key: SecretStr | None = None
    project: str = "english-practice"
    tracing: bool = False


class BaseAppSettings(BaseSettings):
    """The groups every program in this repository reads.

    Subclass it to add the groups only one program needs, and extend
    :meth:`missing_required` with the checks only that program can make.
    """

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)

    # "ignore" rather than "forbid": the env files carry the flat variables too.
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )

    def missing_required(self) -> list[str]:
        """Return human-readable reasons this process cannot do its work.

        Returns:
            One message per misconfiguration; empty when everything shared is
            in place. Subclasses add their own.
        """
        problems: list[str] = []

        if self.llm.active_api_key is None:
            problems.append(
                f"{self.llm.provider.upper()}_API_KEY is not set "
                f"(LLM_PROVIDER={self.llm.provider})"
            )

        if self.langsmith.tracing and secret_value(self.langsmith.api_key) is None:
            problems.append("LANGSMITH_API_KEY is required when tracing is enabled")

        return problems


def settings_env_vars(model: type[BaseModel]) -> tuple[str, ...]:
    """Return the variables currently in the environment that ``model`` reads.

    Each group below is a ``BaseSettings`` in its own right and resolves flat,
    prefixed variables from ``os.environ``, so knowing what a settings model
    would pick up means walking it. This is derived from the model rather than
    hand-listed, which is what stops a new group from being forgotten — the
    caller is a test suite hiding the developer's own environment, and an
    exported ``GEMINI_PROXY`` deciding the outcome of a test that never
    mentions it is a very quiet kind of failure.

    Args:
        model: The root settings class to walk.

    Returns:
        The matching variable names, in no particular order.
    """
    prefixes: list[str] = []
    aliases: list[str] = []

    def walk(group: type[BaseModel]) -> None:
        for field_name, field in group.model_fields.items():
            alias = field.validation_alias
            if isinstance(alias, AliasChoices):
                aliases.extend(str(choice).upper() for choice in alias.choices)

            nested = field.annotation
            if not isinstance(nested, type) or not issubclass(nested, BaseModel):
                continue
            if issubclass(nested, BaseSettings):
                prefixes.append(nested.model_config.get("env_prefix", "").upper())
            else:
                # Plain models are populated through the nested delimiter.
                prefixes.append(f"{field_name.upper()}__")
            # The provider groups hang off LLMSettings, not off the root.
            walk(nested)

    walk(model)
    matched = tuple(prefix for prefix in prefixes if prefix)
    exact = frozenset(aliases)
    return tuple(
        name
        for name in os.environ
        if name.upper().startswith(matched) or name.upper() in exact
    )


def load_settings[T: BaseAppSettings](model: type[T]) -> T:
    """Build a settings model, seeding the environment from the env files first.

    Caching belongs to the caller: each program wraps this in its own
    ``lru_cache``-d ``get_settings()``, so one process reads its configuration
    once and every module sees the same instance.

    Args:
        model: The root settings class to build.

    Returns:
        A fully resolved settings instance.
    """
    load_env()
    return model()
