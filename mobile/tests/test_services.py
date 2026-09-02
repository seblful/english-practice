"""Tests for the dependency wiring.

The behaviour worth pinning down is that a settings change actually reaches the
HTTP pool: the proxy and the timeout are baked in when a client is built, so a
kept client would keep using a proxy the user has just switched off.
"""

from dataclasses import replace

import httpx
import pytest
from practice_core.content import ContentLibrary
from practice_core.errors import ConfigurationError

from practice.config import AppConfig, ConfigStore, ProxyConfig
from practice.services import Services
from practice.stats import StatsStore


def _catalogue_transport(counter: list[int]) -> httpx.MockTransport:
    """Return a transport that counts how often the catalogue was fetched."""

    def handler(_: httpx.Request) -> httpx.Response:
        counter.append(1)
        return httpx.Response(200, json={"data": [{"id": "vendor/model"}]})

    return httpx.MockTransport(handler)


class TestConstruction:
    def test_settings_are_loaded_when_none_are_given(
        self, config_store: ConfigStore, content: ContentLibrary, stats: StatsStore
    ) -> None:
        config_store.save(replace(AppConfig(), max_tokens=1234))

        services = Services(config_store=config_store, content=content, stats=stats)

        assert services.config.max_tokens == 1234


class TestClientLifecycle:
    def test_the_client_is_built_once(self, services: Services) -> None:
        assert services.client is services.client

    def test_the_grader_uses_the_current_client(self, services: Services) -> None:
        grader = services.grader

        assert grader._client is services.client

    async def test_saving_settings_rebuilds_the_client(
        self, services: Services
    ) -> None:
        first = services.client

        await services.update_config(
            replace(
                services.config,
                proxy=ProxyConfig(enabled=True, host="proxy.example", port=8080),
            )
        )

        assert services.client is not first
        assert services.client.config.proxy.url == "http://proxy.example:8080"

    async def test_saving_settings_writes_them(self, services: Services) -> None:
        await services.update_config(replace(services.config, show_rules=False))

        assert services.config_store.load().show_rules is False

    async def test_closing_releases_the_pool(self, services: Services) -> None:
        _ = services.client

        await services.aclose()
        await services.aclose()

        assert services._client is None


class TestListeners:
    async def test_a_plain_listener_is_called(self, services: Services) -> None:
        seen: list[AppConfig] = []
        services.on_config_change(seen.append)

        await services.update_config(replace(services.config, show_rules=False))

        assert seen[0].show_rules is False

    async def test_an_async_listener_is_awaited(self, services: Services) -> None:
        seen: list[bool] = []

        async def listener(config: AppConfig) -> None:
            seen.append(config.show_rules)

        services.on_config_change(listener)

        await services.update_config(replace(services.config, show_rules=False))

        assert seen == [False]


class TestCatalogue:
    async def test_the_catalogue_is_fetched_once_per_provider(
        self,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        fetches: list[int] = []
        services = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=_catalogue_transport(fetches),
        )

        await services.models()
        await services.models()

        assert len(fetches) == 1

    async def test_a_refresh_fetches_again(
        self,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        fetches: list[int] = []
        services = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=_catalogue_transport(fetches),
        )

        await services.models()
        await services.models(refresh=True)

        assert len(fetches) == 2

    def test_nothing_is_cached_before_the_first_fetch(self, services: Services) -> None:
        assert services.cached_models() == []
        assert services.model_info("vendor/model") is None

    async def test_a_fetched_model_can_be_looked_up(
        self,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        services = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=_catalogue_transport([]),
        )

        await services.models()

        assert services.model_info("vendor/model") is not None
        assert services.model_info("absent/model") is None

    async def test_an_unconfigured_provider_refuses_to_fetch(
        self, config_store: ConfigStore, content: ContentLibrary, stats: StatsStore
    ) -> None:
        from practice.providers import Provider  # noqa: PLC0415

        services = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=replace(AppConfig(), provider=Provider.GEMINI),
        )

        with pytest.raises(ConfigurationError, match="API key"):
            await services.models()
