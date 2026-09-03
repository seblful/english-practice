"""Dependency wiring: the one object every screen is handed.

The screens never build a content library, a provider client or a stats store;
they reach them through :class:`Services`. That is what keeps one HTTP
connection pool for the whole app — and what lets a test hand a screen a fake
without patching module globals.

Changing a setting has to reach the pool: the proxy and the timeout are baked
into an :class:`~practice_app.llm.LLMClient` when it is built, so a client
whose settings have been typed over is retired rather than left answering with
them. That is why :attr:`Services.config` is read-only and every edit arrives
through :meth:`Services.stage` or :meth:`Services.update_config` — the screen
that edits settings used to assign the attribute, and the client went on
holding whichever object it was built from.
"""

import httpx
from practice_core.content import ContentLibrary

from practice_app.config import AppConfig, ConfigStore
from practice_app.grading import Grader
from practice_app.llm import LLMClient
from practice_app.providers import ModelInfo, Provider
from practice_app.stats import StatsStore

__all__ = ["Services"]


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
        self._config = config if config is not None else config_store.load()
        self._transport = transport
        self._client: LLMClient | None = None
        # Clients whose settings have been typed over. Closing a pool is a
        # coroutine and staging is not, so they wait here for the next await.
        self._retired: list[LLMClient] = []
        # Catalogues are per provider and cost a round trip, so a fetched one
        # is kept for as long as the app runs.
        self._catalogues: dict[Provider, list[ModelInfo]] = {}

    # ------------------------------------------------------------------
    # Provider access
    # ------------------------------------------------------------------

    @property
    def client(self) -> LLMClient:
        """Return a provider client built from the settings now in force.

        The key, the proxy and the timeout are baked in when a client is
        built, so one left standing after an edit answers with the settings
        the user has just typed over -- which is how "Test connection" came to
        report on the previous API key.
        """
        if self._client is not None and self._client.config is not self._config:
            self._retire_client()
        if self._client is None:
            self._client = LLMClient(self._config, transport=self._transport)
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

    @property
    def config(self) -> AppConfig:
        """Return the settings in force, staged edits included."""
        return self._config

    def stage(self, config: AppConfig) -> None:
        """Hold an edit without saving it.

        This is the only way in. The settings screen used to reach the
        attribute directly, and did it two ways: three fields replaced the
        object, which left the live client holding the old one, and four
        mutated the proxy in place, which put a half-typed host into the pool
        the app was already making requests through.

        Args:
            config: The settings to hold. Saved by :meth:`update_config`.
        """
        self._config = config

    async def update_config(self, config: AppConfig) -> None:
        """Save new settings and retire anything built from the old.

        Args:
            config: The settings to store.
        """
        self.stage(config)
        self.config_store.save(config)
        self._retire_client()
        await self._close_retired()

    async def aclose(self) -> None:
        """Release every provider connection pool this object opened."""
        self._retire_client()
        await self._close_retired()

    def _retire_client(self) -> None:
        """Set the current client aside for closing."""
        if self._client is not None:
            self._retired.append(self._client)
            self._client = None

    async def _close_retired(self) -> None:
        """Close the pools of clients whose settings have been typed over."""
        retired, self._retired = self._retired, []
        for client in retired:
            await client.aclose()
