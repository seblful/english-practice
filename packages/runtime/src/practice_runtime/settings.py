"""The settings both programs read."""

import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal

from dotenv import dotenv_values
from practice_core.providers import DEFAULT_PROVIDER, Provider
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BASE_DIR",
    "ENV_FILENAME",
    "LAYOUT",
    "RENAMED",
    "AppSettings",
    "BaseAppSettings",
    "GeminiSettings",
    "LLMAppSettings",
    "LLMSettings",
    "LangSmithSettings",
    "LogLevel",
    "LoggingSettings",
    "OpenRouterSettings",
    "PathSettings",
    "ProviderSettings",
    "env_var",
    "group_config",
    "load_env",
    "load_settings",
    "project_root",
    "renamed_variables",
    "secret_value",
    "settings_env_vars",
]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_DEFAULT_ENVIRONMENT = "development"
# Read before any settings exist, so not a field; APP_ like the group it joins.
_ROOT_VAR = "APP_PROJECT_ROOT"

#: The one file that seeds the environment, at the project root.
ENV_FILENAME = ".env"

#: Variables older versions read, and what replaced each; "" when nothing did.
RENAMED: Final[Mapping[str, str]] = MappingProxyType(
    {
        "APP__ENVIRONMENT": "APP_ENVIRONMENT",
        "APP__APP_NAME": "APP_NAME",
        "APP__PROJECT_ROOT": "APP_PROJECT_ROOT",
        "LOGGING__FILE_LEVEL": "LOGGING_FILE_LEVEL",
        "LOGGING__CONSOLE_LEVEL": "LOGGING_CONSOLE_LEVEL",
        "LOGGING__LOG_FILE": "LOGGING_FILE",
        "DATABASE_PATH": "PATHS_DATABASE_PATH",
        "GEMINI_MODEL": "LLM_MODEL",
        "GEMINI_TEMPERATURE": "LLM_TEMPERATURE",
        "GEMINI_MAX_TOKENS": "LLM_MAX_TOKENS",
        "GEMINI_TOP_P": "LLM_TOP_P",
        "OPENROUTER_MODEL": "LLM_MODEL",
        "OPENROUTER_TEMPERATURE": "LLM_TEMPERATURE",
        "OPENROUTER_MAX_TOKENS": "LLM_MAX_TOKENS",
        "OPENROUTER_BASE_URL": "",
        "DECISION_ROUTE": "GRADER_PROVIDER",
        "DECISION_MODEL": "GRADER_MODEL",
        "DECISION_REQUEST_TIMEOUT": "GRADER_REQUEST_TIMEOUT",
        "DECISION_MAX_RETRIES": "GRADER_MAX_RETRIES",
        "DECISION_PROXY": "GEMINI_PROXY or OPENROUTER_PROXY",
        "DECISION_GOOGLE_API_KEY": "GEMINI_API_KEY",
        "DECISION_OPENROUTER_API_KEY": "OPENROUTER_API_KEY",
        "OCR_API_KEY": "MISTRAL_API_KEY",
        "DASHSCOPE_API_KEY": "",
        "DASHSCOPE_MODEL": "",
    }
)


def group_config(name: str) -> SettingsConfigDict:
    """Return the config of the settings group read from ``<NAME>_*`` variables.

    An empty variable, as a copied .env.example leaves it, means unset.
    """
    return SettingsConfigDict(
        env_prefix=f"{name.upper()}_", case_sensitive=False, env_ignore_empty=True
    )


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Return the repository root: the directory holding ``data/`` and ``.env``."""
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
    """Return the plain text behind an optional secret."""
    if secret is None:
        return None
    return secret.get_secret_value().strip() or None


def load_env(base_dir: Path | None = None) -> dict[str, str]:
    """Seed ``os.environ`` from ``.env``; a missing file is no error."""
    env_file = (base_dir or BASE_DIR) / ENV_FILENAME
    if not env_file.exists():
        return {}

    from_file = {
        key: value
        for key, value in dotenv_values(env_file, encoding="utf-8").items()
        if value is not None
    }
    applied = {k: v for k, v in from_file.items() if k not in os.environ}
    os.environ.update(applied)
    return applied


class AppSettings(BaseSettings):
    """Application identity and environment."""

    model_config = group_config("app")

    name: str = Field(default="english-practice", description="Application name")
    environment: str = Field(
        default=_DEFAULT_ENVIRONMENT, description="Environment name"
    )

    @property
    def is_production(self) -> bool:
        """Whether this process is running a deployment rather than a laptop."""
        return self.environment == "production"


class LoggingSettings(BaseSettings):
    """Logging destinations and verbosity."""

    model_config = group_config("logging")

    file_level: LogLevel = Field(default="INFO", description="File log level")
    console_level: LogLevel = Field(default="INFO", description="Console log level")
    file: Path = Field(default=Path("logs/app.log"), description="Log file path")


class PathSettings(BaseSettings):
    """Filesystem layout for source material, generated content, and the database."""

    model_config = group_config("paths")

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

    database_path: Path = Field(default=_DERIVED, description="SQLite database file")

    @model_validator(mode="after")
    def _derive_unset_paths(self) -> "PathSettings":
        """Build every path the caller did not set from the one above it."""
        for name, parent, segment in LAYOUT:
            if name not in self.model_fields_set:
                setattr(self, name, getattr(self, parent) / segment)
        return self

    def create_directories(self) -> None:
        """Create every configured directory."""
        for path in self.model_dump().values():
            if (
                isinstance(path, Path)
                and not path.suffix  # Skip files (paths with extensions)
            ):
                path.mkdir(parents=True, exist_ok=True)


class ProviderSettings(BaseSettings):
    """A model provider's credentials, shared by everything that calls it."""

    # An empty variable, as a copied .env.example leaves it, means unset.
    model_config = SettingsConfigDict(case_sensitive=False, env_ignore_empty=True)

    api_key: SecretStr | None = None
    proxy: str | None = Field(
        default=None, description="HTTP or SOCKS proxy for this provider's calls"
    )

    @property
    def key(self) -> str | None:
        """Return the API key, or None when it is unset or blank."""
        return secret_value(self.api_key)

    @property
    def key_variable(self) -> str:
        """Return the variable this provider's key is read from."""
        return env_var(self, "api_key")


class GeminiSettings(ProviderSettings):
    """Google AI Studio: Gemini chat models and Gemini Decision."""

    model_config = group_config("gemini")


class OpenRouterSettings(ProviderSettings):
    """OpenRouter: many vendors' models behind one key."""

    model_config = group_config("openrouter")


#: The chat model each provider runs when LLM_MODEL is unset.
_CHAT_MODELS: Final = {
    Provider.GEMINI: "gemini-2.5-flash-lite",
    Provider.OPENROUTER: "google/gemma-4-26b-a4b-it",
}


class LLMSettings(BaseSettings):
    """The chat model the content pipeline calls, and how it is sampled."""

    model_config = group_config("llm")

    provider: Provider = DEFAULT_PROVIDER
    model: str | None = Field(
        default=None, description="The provider's default chat model when unset"
    )
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    request_timeout: float = Field(
        default=60.0, gt=0, description="Per-request timeout in seconds"
    )
    max_retries: int = Field(
        default=2, ge=0, description="Retries for transient provider failures"
    )

    @property
    def active_model(self) -> str:
        """Return the model to call: the one set, or the provider's default."""
        return (self.model or "").strip() or _CHAT_MODELS[self.provider]


class LangSmithSettings(BaseSettings):
    """LangSmith tracing settings."""

    model_config = group_config("langsmith")

    api_key: SecretStr | None = None
    project: str = "english-practice"
    tracing: bool = False


class BaseAppSettings(BaseSettings):
    """The groups every program in this repository reads.

    Every group is read from variables named ``<GROUP>_<FIELD>``: the
    ``telegram.bot_token`` field is ``TELEGRAM_BOT_TOKEN``, and so on.
    """

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)

    # "ignore": the env files carry every program's variables.
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    def credentials(self, provider: Provider) -> ProviderSettings:
        """Return the key and proxy configured for ``provider``."""
        if provider is Provider.OPENROUTER:
            return self.openrouter
        return self.gemini

    def missing_key(self, provider: Provider, chosen_by: str) -> str | None:
        """Return why ``provider`` cannot be called, naming what chose it."""
        credentials = self.credentials(provider)
        if credentials.key is not None:
            return None
        return f"{credentials.key_variable} is not set ({chosen_by}={provider})"

    def missing_required(self) -> list[str]:
        """Return human-readable reasons this process cannot do its work."""
        problems = renamed_variables()

        if self.langsmith.tracing and secret_value(self.langsmith.api_key) is None:
            problems.append(
                f"{env_var(self.langsmith, 'api_key')} is required when tracing "
                "is enabled"
            )

        return problems


class LLMAppSettings(BaseAppSettings):
    """The shared groups, plus a chat model, for a program that calls one."""

    llm: LLMSettings = Field(default_factory=LLMSettings)

    @property
    def llm_credentials(self) -> ProviderSettings:
        """Return the credentials of the chat model's provider."""
        return self.credentials(self.llm.provider)

    def missing_required(self) -> list[str]:
        """Return the shared problems, plus a missing provider key."""
        problems = super().missing_required()

        missing = self.missing_key(self.llm.provider, env_var(self.llm, "provider"))
        if missing is not None:
            problems.append(missing)

        return problems


def env_var(group: BaseSettings | type[BaseSettings], field: str) -> str:
    """Return the variable that sets ``field`` of a settings group."""
    prefix = str(group.model_config.get("env_prefix", ""))
    return f"{prefix}{field}".upper()


def renamed_variables() -> list[str]:
    """Explain each variable set in the environment that is no longer read."""
    problems: list[str] = []
    present = {name.upper() for name in os.environ}
    for old, new in RENAMED.items():
        if old not in present:
            continue
        if new:
            problems.append(f"{old} is no longer read: rename it to {new}")
        else:
            problems.append(f"{old} is no longer read: remove it")
    return problems


def settings_env_vars(model: type[BaseSettings]) -> tuple[str, ...]:
    """Return the variables currently in the environment that ``model`` reads.

    Renamed ones count too: they are about this model, if only to be refused.
    """
    prefixes = tuple(
        env_var(nested, "")
        for field in model.model_fields.values()
        if isinstance(nested := field.annotation, type)
        and issubclass(nested, BaseSettings)
    )
    matched = tuple(prefix for prefix in prefixes if prefix)
    return tuple(
        name
        for name in os.environ
        if name.upper().startswith(matched) or name.upper() in RENAMED
    )


def load_settings[T: BaseAppSettings](model: type[T]) -> T:
    """Build a settings model, seeding the environment from the env files first."""
    load_env()
    return model()
