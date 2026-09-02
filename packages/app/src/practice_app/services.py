"""Dependency wiring: the one object every screen is handed.

The screens never build a content library, a provider client or a stats store;
they reach them through :class:`Services`. That is what keeps one HTTP
connection pool for the whole app — and what lets a test hand a screen a fake
without patching module globals.

Changing a setting has to reach the pool: the proxy and the timeout are baked
into an :class:`~practice.llm.LLMClient` when it is built, so
:meth:`Services.update_config` closes the old one instead of leaving requests
going through a proxy the user has just turned off.
"""

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
from practice_core.content import ContentLibrary

from practice_app.config import AppConfig, ConfigStore
from practice_app.grading import Grader
from practice_app.llm import LLMClient
from practice_app.providers import ModelInfo, Provider
from practice_app.stats import StatsStore

__all__ = ["Services"]

ConfigListener = Callable[[AppConfig], Coroutine[Any, Any, None] | None]


class Services:
    """Everything the screens need, built once for the app."""

    def __init__(
        self,
        *,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize the services.

        Args:
            config_store: Where settings are read from and written to.
            content: The bundled exercise database.
            stats: The progress database.
            config: Settings to start with. Loaded from the store when omitted.
            transport: HTTP transport for provider calls, for tests.
        """
        self.config_store = config_store
        self.content = content
        self.stats = stats
        self.config = config if config is not None else config_store.load()
        self._transport = transport
        self._client: LLMClient | None = None
        self._listeners: list[ConfigListener] = []
        # Catalogues are per provider and cost a round trip, so a fetched one
        # is kept for as long as the app runs.
        self._catalogues: dict[Provider, list[ModelInfo]] = {}

    # ------------------------------------------------------------------
    # Provider access
    # ------------------------------------------------------------------

    @property
    def client(self) -> LLMClient:
        """Return the provider client, building it on first use."""
        if self._client is None:
            self._client = LLMClient(self.config, transport=self._transport)
        return self._client

    @property
    def grader(self) -> Grader:
        """Return a grader on the current provider client."""
        return Grader(self.client)

    async def models(self, *, refresh: bool = False) -> list[ModelInfo]:
        """Return the current provider's catalogue, fetching it if needed.

        Args:
            refresh: Fetch again even when a catalogue is already held, which
                is what the picker's refresh button asks for.

        Returns:
            The models, sorted by id.

        Raises:
            ConfigurationError: If the provider needs a key and none is set.
            ProviderError: If the catalogue cannot be fetched.
        """
        provider = self.config.provider
        if refresh or provider not in self._catalogues:
            self._catalogues[provider] = await self.client.list_models()
        return self._catalogues[provider]

    def cached_models(self) -> list[ModelInfo]:
        """Return the current provider's catalogue if one was already fetched.

        Returns:
            The models, or an empty list when nothing has been fetched.
        """
        return self._catalogues.get(self.config.provider, [])

    def model_info(self, model_id: str) -> ModelInfo | None:
        """Return what is known about one model of the current provider.

        Args:
            model_id: The model to look up.

        Returns:
            Its catalogue entry, or ``None`` when the catalogue has not been
            fetched or does not list it.
        """
        return next(
            (model for model in self.cached_models() if model.id == model_id),
            None,
        )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def on_config_change(self, listener: ConfigListener) -> None:
        """Register a callback to run after settings are saved.

        Args:
            listener: Called with the new settings. May be a coroutine
                function, in which case the caller awaits it.
        """
        self._listeners.append(listener)

    async def update_config(self, config: AppConfig) -> None:
        """Save new settings and rebuild anything that depended on the old.

        Args:
            config: The settings to store.
        """
        self.config = config
        self.config_store.save(config)

        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

        for listener in self._listeners:
            result = listener(config)
            if result is not None:
                await result

    async def aclose(self) -> None:
        """Release the provider connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
