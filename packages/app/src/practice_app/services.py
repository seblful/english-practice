"""Dependency wiring: the one object every screen is handed."""

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
        """Initialize the services."""
        self.config_store = config_store
        self.content = content
        self.stats = stats
        self._config = config if config is not None else config_store.load()
        self._transport = transport
        self._client: LLMClient | None = None
        # Closing a pool is a coroutine and staging is not, so they wait for an await.
        self._retired: list[LLMClient] = []
        # A catalogue costs a round trip, so a fetched one is kept for the run.
        self._catalogues: dict[Provider, list[ModelInfo]] = {}

    # --- Provider access ---

    @property
    def client(self) -> LLMClient:
        """Return a provider client built from the settings now in force."""
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
        """Return the current provider's catalogue, fetching it if needed."""
        provider = self.config.provider
        if refresh or provider not in self._catalogues:
            self._catalogues[provider] = await self.client.list_models()
        return self._catalogues[provider]

    def cached_models(self) -> list[ModelInfo]:
        """Return the current provider's catalogue if one was already fetched."""
        return self._catalogues.get(self.config.provider, [])

    def model_info(self, model_id: str) -> ModelInfo | None:
        """Return what is known about one model of the current provider."""
        return next(
            (model for model in self.cached_models() if model.id == model_id),
            None,
        )

    # --- Settings ---

    @property
    def config(self) -> AppConfig:
        """Return the settings in force, staged edits included."""
        return self._config

    def stage(self, config: AppConfig) -> None:
        """Hold an edit without saving it."""
        self._config = config

    async def update_config(self, config: AppConfig) -> None:
        """Save new settings and retire anything built from the old."""
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
