"""User settings, and the JSON file they live in."""

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from practice_core.providers import DEFAULT_PROVIDER, Provider

from practice_app.catalogue import is_decision_model

__all__ = [
    "MAX_PORT",
    "AppConfig",
    "ConfigStore",
    "ProviderConfig",
    "ProxyConfig",
    "ThemeChoice",
]

SETTINGS_FILENAME = "settings.json"
#: 1 kept a chat provider each; 2 one Google key; 3 a key and model per route;
#: 4 names those routes after the providers, Google as "gemini".
SETTINGS_VERSION: Final = 4

DEFAULT_TIMEOUT = 90.0

PROXY_SCHEMES = ("http", "https", "socks5")

#: Public because the settings screen rejects what is typed, not only stored.
MAX_PORT = 65535


class ThemeChoice(StrEnum):
    """The three values :attr:`AppConfig.theme` can take."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


def _as_float(value: Any, fallback: float) -> float:
    """Return ``value`` as a float, falling back on anything unusable."""
    return float(value) if isinstance(value, (int, float)) else fallback


def _as_str(value: Any) -> str:
    """Return ``value`` as a stripped string, or empty for anything else."""
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """An optional HTTP or SOCKS5 proxy, with optional credentials."""

    enabled: bool = False
    scheme: str = "http"
    host: str = ""
    port: int | None = None
    username: str = ""
    password: str = ""

    @property
    def is_complete(self) -> bool:
        """Whether the proxy has enough detail to be usable."""
        return bool(self.host) and self.port is not None

    @property
    def url(self) -> str | None:
        """Return the proxy URL httpx should use, or ``None``."""
        if not self.enabled or not self.is_complete:
            return None

        credentials = ""
        if self.username:
            from urllib.parse import quote  # noqa: PLC0415

            user = quote(self.username, safe="")
            secret = quote(self.password, safe="")
            credentials = f"{user}:{secret}@" if secret else f"{user}@"

        return f"{self.scheme}://{credentials}{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON form of this proxy."""
        return {
            "enabled": self.enabled,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ProxyConfig":
        """Build a proxy from stored JSON, ignoring anything unexpected."""
        if not isinstance(data, dict):
            return cls()

        scheme = _as_str(data.get("scheme")).lower()
        port = data.get("port")
        return cls(
            enabled=bool(data.get("enabled", False)),
            scheme=scheme if scheme in PROXY_SCHEMES else "http",
            host=_as_str(data.get("host")),
            port=port if isinstance(port, int) and 0 < port <= MAX_PORT else None,
            username=_as_str(data.get("username")),
            password=data.get("password")
            if isinstance(data.get("password"), str)
            else "",
        )


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """What one provider needs: a key, and the decision model to ask."""

    api_key: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON form of this provider's settings."""
        return {"api_key": self.api_key, "model": self.model}

    @classmethod
    def from_dict(cls, data: Any, *, provider: Provider) -> "ProviderConfig":
        """Build a provider's settings from stored JSON, defaulting its model."""
        data = data if isinstance(data, dict) else {}
        return cls(
            # A key pasted with a stray newline builds an illegal header value.
            api_key=_as_str(data.get("api_key")),
            model=_as_str(data.get("model")) or provider.decision_model,
        )


def _default_providers() -> dict[Provider, ProviderConfig]:
    """Return every provider with no key and its own default model."""
    return {
        provider: ProviderConfig(model=provider.decision_model) for provider in Provider
    }


@dataclass(slots=True)
class AppConfig:
    """Everything the user can change, in one object."""

    provider: Provider = DEFAULT_PROVIDER
    providers: dict[Provider, ProviderConfig] = field(
        default_factory=_default_providers
    )
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    show_rules: bool = True
    theme: ThemeChoice = ThemeChoice.SYSTEM
    request_timeout: float = DEFAULT_TIMEOUT

    @property
    def active(self) -> ProviderConfig:
        """Return the selected provider's settings."""
        return self.providers.get(self.provider) or ProviderConfig(
            model=self.provider.decision_model
        )

    def with_active(self, **changes: Any) -> "AppConfig":
        """Return this config with the selected provider's fields changed."""
        providers = dict(self.providers)
        providers[self.provider] = replace(self.active, **changes)
        return replace(self, providers=providers)

    def missing(self) -> list[str]:
        """Return one message per reason grading cannot run yet."""
        problems: list[str] = []
        if not self.active.api_key:
            problems.append(f"{self.provider.label} API key is not set")
        if not self.active.model:
            problems.append("No model selected")
        if self.proxy.enabled and not self.proxy.is_complete:
            problems.append("Proxy is enabled but has no host and port")
        return problems

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON form of every setting."""
        return {
            "version": SETTINGS_VERSION,
            "provider": self.provider.value,
            "providers": {
                provider.value: config.to_dict()
                for provider, config in self.providers.items()
            },
            "proxy": self.proxy.to_dict(),
            "show_rules": self.show_rules,
            "theme": self.theme.value,
            "request_timeout": self.request_timeout,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        """Build a config from stored JSON, migrating an older file first."""
        if not isinstance(data, dict):
            return cls()
        # Each step ends on the next version, so an old file walks the chain.
        while (migrate := _MIGRATIONS.get(data.get("version"))) is not None:
            data = migrate(data)

        stored = data.get("providers")
        stored = stored if isinstance(stored, dict) else {}
        try:
            provider = Provider(_as_str(data.get("provider")).lower())
        except ValueError:
            provider = DEFAULT_PROVIDER
        try:
            theme = ThemeChoice(_as_str(data.get("theme")).lower())
        except ValueError:
            theme = ThemeChoice.SYSTEM
        return cls(
            provider=provider,
            providers={
                known: ProviderConfig.from_dict(stored.get(known.value), provider=known)
                for known in Provider
            },
            proxy=ProxyConfig.from_dict(data.get("proxy")),
            show_rules=bool(data.get("show_rules", True)),
            theme=theme,
            request_timeout=_as_float(data.get("request_timeout"), DEFAULT_TIMEOUT),
        )


def _provider_settings(api_key: Any, model: Any, provider: Provider) -> dict[str, Any]:
    """Return one provider's stored settings, keeping the model only if it decides.

    A chat model cannot answer a decision, so it gives way to the default.
    """
    stored = _as_str(model)
    return {
        "api_key": api_key,
        "model": stored if is_decision_model(stored) else provider.decision_model,
    }


def _with_providers(
    data: dict[str, Any], openrouter: dict[str, Any], gemini: dict[str, Any]
) -> dict[str, Any]:
    """Return a version-3 file, on the default provider unless only the other has a key.

    Version 3 is the last that says "route"; the step after it renames.
    """
    keyed = {
        provider
        for provider, settings in (
            (Provider.OPENROUTER, openrouter),
            (Provider.GEMINI, gemini),
        )
        if _as_str(settings["api_key"])
    }
    # Don't strand a working user on a provider with no key.
    chosen = DEFAULT_PROVIDER if DEFAULT_PROVIDER in keyed or not keyed else keyed.pop()
    return {
        **data,
        "version": 3,
        "route": _V3_ROUTES[chosen],
        "routes": {
            _V3_ROUTES[Provider.OPENROUTER]: openrouter,
            _V3_ROUTES[Provider.GEMINI]: gemini,
        },
    }


def _from_version_1(data: dict[str, Any]) -> dict[str, Any]:
    """Return a version-1 file, which kept a key and chat model per provider.

    OpenRouter's key carries over to OpenRouter and Gemini's to Gemini; the
    OpenAI key has nowhere to go.
    """
    providers = data.get("providers")
    providers = providers if isinstance(providers, dict) else {}

    def provider(name: str) -> dict[str, Any]:
        stored = providers.get(name)
        return stored if isinstance(stored, dict) else {}

    openrouter, gemini = provider("openrouter"), provider("gemini")
    return _with_providers(
        data,
        _provider_settings(
            openrouter.get("api_key"), openrouter.get("model"), Provider.OPENROUTER
        ),
        _provider_settings(gemini.get("api_key"), gemini.get("model"), Provider.GEMINI),
    )


def _from_version_2(data: dict[str, Any]) -> dict[str, Any]:
    """Return a version-2 file, which kept one Google key and model at the top."""
    return _with_providers(
        data,
        _provider_settings("", "", Provider.OPENROUTER),
        _provider_settings(data.get("api_key"), data.get("model"), Provider.GEMINI),
    )


#: What version 3 stored for each provider: its Google side was "google".
_V3_ROUTES: Final = {Provider.OPENROUTER: "openrouter", Provider.GEMINI: "google"}


def _from_version_3(data: dict[str, Any]) -> dict[str, Any]:
    """Return a version-3 file, whose routes were "openrouter" and "google"."""
    by_route = {route: provider.value for provider, route in _V3_ROUTES.items()}
    stored = data.get("routes")
    stored = stored if isinstance(stored, dict) else {}
    chosen = _as_str(data.get("route")).lower()
    migrated = {
        key: value for key, value in data.items() if key not in {"route", "routes"}
    }
    return {
        **migrated,
        "version": 4,
        "provider": by_route.get(chosen, chosen),
        "providers": {
            by_route[route]: settings
            for route, settings in stored.items()
            if route in by_route
        },
    }


_MIGRATIONS: Final[dict[object, Callable[[dict[str, Any]], dict[str, Any]]]] = {
    1: _from_version_1,
    2: _from_version_2,
    3: _from_version_3,
}


class ConfigStore:
    """Reads and writes the settings file."""

    def __init__(self, path: Path) -> None:
        """Initialize the store."""
        self.path = path

    def load(self) -> AppConfig:
        """Return the stored settings, or the defaults."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return AppConfig()

        try:
            return AppConfig.from_dict(json.loads(raw))
        except json.JSONDecodeError:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Write the settings, replacing the file atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config.to_dict(), indent=2, sort_keys=True)

        handle, temp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=".settings-", suffix=".json"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(payload)
            Path(temp_name).replace(self.path)
        except OSError:
            Path(temp_name).unlink(missing_ok=True)
            raise
