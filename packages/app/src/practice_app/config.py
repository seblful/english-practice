"""User settings, and the JSON file they live in.

Settings are per-provider rather than global: switching from OpenRouter to
Gemini to compare graders must not make the user retype a key and hunt for a
model again, so every provider keeps its own key, model and thinking level and
:attr:`AppConfig.provider` only says which of them is live.

The file sits in the app's private storage directory, unencrypted — the same
place, and the same protection, that Android's own shared preferences would
give it. Nothing here is ever logged.
"""

import json
import os
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from practice_app.providers import Provider, ThinkingLevel

__all__ = [
    "AppConfig",
    "ConfigStore",
    "ProviderConfig",
    "ProxyConfig",
    "ThemeChoice",
]

SETTINGS_FILENAME = "settings.json"

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 90.0

PROXY_SCHEMES = ("http", "https", "socks5")

_MAX_PORT = 65535


class ThemeChoice:
    """The three values :attr:`AppConfig.theme` can take."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"

    ALL = (SYSTEM, LIGHT, DARK)


def _as_float(value: Any, fallback: float) -> float:
    """Return ``value`` as a float, falling back on anything unusable."""
    return float(value) if isinstance(value, (int, float)) else fallback


def _as_int(value: Any, fallback: int) -> int:
    """Return ``value`` as an int, falling back on anything unusable."""
    return int(value) if isinstance(value, (int, float)) else fallback


def _as_str(value: Any) -> str:
    """Return ``value`` as a stripped string, or empty for anything else."""
    return value.strip() if isinstance(value, str) else ""


@dataclass(slots=True)
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
        """Return the proxy URL httpx should use, or ``None``.

        Credentials are percent-encoded: a password with an ``@`` or a ``:`` in
        it would otherwise split the authority and point the proxy elsewhere.

        Returns:
            The full proxy URL, or ``None`` when the proxy is off or
            incomplete.
        """
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
        """Build a proxy from stored JSON, ignoring anything unexpected.

        Args:
            data: The decoded ``proxy`` object, whatever it turned out to be.

        Returns:
            The proxy, with defaults wherever the stored value was unusable.
        """
        if not isinstance(data, dict):
            return cls()

        scheme = _as_str(data.get("scheme")).lower()
        port = data.get("port")
        return cls(
            enabled=bool(data.get("enabled", False)),
            scheme=scheme if scheme in PROXY_SCHEMES else "http",
            host=_as_str(data.get("host")),
            port=port if isinstance(port, int) and 0 < port <= _MAX_PORT else None,
            username=_as_str(data.get("username")),
            password=data.get("password")
            if isinstance(data.get("password"), str)
            else "",
        )


@dataclass(slots=True)
class ProviderConfig:
    """What one provider needs: a key, a model, and how hard it should think."""

    api_key: str = ""
    model: str = ""
    thinking: ThinkingLevel = ThinkingLevel.OFF
    # Cached from the catalogue so a restart still knows whether the chosen
    # model reasons, without re-fetching several hundred entries to find out.
    model_supports_thinking: bool = False
    model_supports_json: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON form of this provider's settings."""
        return {
            "api_key": self.api_key,
            "model": self.model,
            "thinking": self.thinking.value,
            "model_supports_thinking": self.model_supports_thinking,
            "model_supports_json": self.model_supports_json,
        }

    @classmethod
    def from_dict(cls, data: Any, *, provider: Provider) -> "ProviderConfig":
        """Build provider settings from stored JSON.

        Args:
            data: The decoded object for one provider.
            provider: Which provider the entry belongs to, for the defaults to
                fall back on.

        Returns:
            The settings, with defaults wherever the stored value was unusable.
        """
        default = _default_provider(provider)
        if not isinstance(data, dict):
            return default

        raw_level = _as_str(data.get("thinking")).lower()
        try:
            thinking = ThinkingLevel(raw_level)
        except ValueError:
            thinking = ThinkingLevel.OFF

        model = _as_str(data.get("model")) or default.model
        # A file written before the app recorded capabilities says nothing
        # about them, and assuming "no" for the model the app picked itself is
        # what left a fresh install insisting its own default cannot think. So
        # the known answer wins while the stored model is still that one.
        stored_thinking = data.get("model_supports_thinking")
        supports_thinking = (
            default.model_supports_thinking
            if stored_thinking is None and model == default.model
            else bool(stored_thinking)
        )

        return cls(
            # Stripped here too: a key pasted with a stray newline would
            # otherwise build an illegal header value.
            api_key=_as_str(data.get("api_key")).strip(),
            model=model,
            thinking=thinking,
            model_supports_thinking=supports_thinking,
            model_supports_json=bool(data.get("model_supports_json", False)),
        )


def _default_provider(provider: Provider) -> ProviderConfig:
    """Return the settings a provider starts from, before anything is stored.

    Args:
        provider: The provider to describe.

    Returns:
        Its default model, and what that model is known to support.
    """
    return ProviderConfig(
        model=provider.default_model,
        model_supports_thinking=provider.default_model_reasons,
    )


def _default_providers() -> dict[Provider, ProviderConfig]:
    """Return one empty configuration per provider, with its default model."""
    return {provider: _default_provider(provider) for provider in Provider}


@dataclass(slots=True)
class AppConfig:
    """Everything the user can change, in one object."""

    provider: Provider = Provider.OPENROUTER
    providers: dict[Provider, ProviderConfig] = field(
        default_factory=_default_providers
    )
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    show_rules: bool = True
    theme: str = ThemeChoice.SYSTEM
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    request_timeout: float = DEFAULT_TIMEOUT

    @property
    def active(self) -> ProviderConfig:
        """Return the selected provider's settings, creating them if needed."""
        return self.providers.setdefault(
            self.provider, _default_provider(self.provider)
        )

    @property
    def is_ready(self) -> bool:
        """Whether grading can be attempted at all."""
        return not self.missing()

    def missing(self) -> list[str]:
        """Return one message per reason grading cannot run yet.

        Returns:
            Human-readable problems; empty when the app is configured.
        """
        problems: list[str] = []
        active = self.active
        if not active.api_key:
            problems.append(f"{self.provider.label} API key is not set")
        if not active.model:
            problems.append("No model selected")
        if self.proxy.enabled and not self.proxy.is_complete:
            problems.append("Proxy is enabled but has no host and port")
        return problems

    def with_active(self, **changes: Any) -> "AppConfig":
        """Return this config with the active provider's fields changed.

        Args:
            **changes: Fields of :class:`ProviderConfig` to replace.

        Returns:
            A new config; the original is left alone.
        """
        providers = dict(self.providers)
        providers[self.provider] = replace(self.active, **changes)
        return replace(self, providers=providers)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON form of every setting."""
        return {
            "version": 1,
            "provider": self.provider.value,
            "providers": {
                provider.value: config.to_dict()
                for provider, config in self.providers.items()
            },
            "proxy": self.proxy.to_dict(),
            "show_rules": self.show_rules,
            "theme": self.theme,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "request_timeout": self.request_timeout,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        """Build a config from stored JSON.

        A settings file written by a newer version, hand-edited, or truncated
        by a crash must never stop the app from starting, so every field falls
        back to its default independently.

        Args:
            data: The decoded settings file.

        Returns:
            The settings.
        """
        if not isinstance(data, dict):
            return cls()

        try:
            provider = Provider(_as_str(data.get("provider")).lower())
        except ValueError:
            provider = Provider.OPENROUTER

        stored = data.get("providers")
        stored = stored if isinstance(stored, dict) else {}
        providers = {
            known: ProviderConfig.from_dict(stored.get(known.value), provider=known)
            for known in Provider
        }

        theme = _as_str(data.get("theme")).lower()
        return cls(
            provider=provider,
            providers=providers,
            proxy=ProxyConfig.from_dict(data.get("proxy")),
            show_rules=bool(data.get("show_rules", True)),
            theme=theme if theme in ThemeChoice.ALL else ThemeChoice.SYSTEM,
            temperature=_as_float(data.get("temperature"), DEFAULT_TEMPERATURE),
            max_tokens=_as_int(data.get("max_tokens"), DEFAULT_MAX_TOKENS),
            request_timeout=_as_float(data.get("request_timeout"), DEFAULT_TIMEOUT),
        )


class ConfigStore:
    """Reads and writes the settings file."""

    def __init__(self, path: Path) -> None:
        """Initialize the store.

        Args:
            path: The settings file. Its directory is created on save.
        """
        self.path = path

    def load(self) -> AppConfig:
        """Return the stored settings, or the defaults.

        A file that cannot be read or parsed is treated as absent rather than
        as an error: the alternative is an app that will not start until
        someone with a file manager deletes it.

        Returns:
            The settings.
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return AppConfig()

        try:
            return AppConfig.from_dict(json.loads(raw))
        except json.JSONDecodeError:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Write the settings, replacing the file atomically.

        The app writes on every toggle, so a write interrupted by the OS
        killing a backgrounded app must not leave a half-written file behind.

        Args:
            config: The settings to store.
        """
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
