"""Tests for the settings model and the file it lives in."""

import json
import os
from pathlib import Path

import pytest

from practice_app.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT,
    AppConfig,
    ConfigStore,
    ProviderConfig,
    ProxyConfig,
    ThemeChoice,
)
from practice_app.providers import Provider, ThinkingLevel


class TestProxyUrl:
    def test_a_disabled_proxy_has_no_url(self) -> None:
        proxy = ProxyConfig(enabled=False, host="proxy.example", port=8080)

        assert proxy.url is None

    def test_an_incomplete_proxy_has_no_url(self) -> None:
        assert ProxyConfig(enabled=True, host="proxy.example").url is None
        assert ProxyConfig(enabled=True, port=8080).url is None

    def test_an_open_proxy(self) -> None:
        proxy = ProxyConfig(enabled=True, host="proxy.example", port=8080)

        assert proxy.url == "http://proxy.example:8080"

    def test_credentials_are_included(self) -> None:
        proxy = ProxyConfig(
            enabled=True,
            scheme="socks5",
            host="proxy.example",
            port=1080,
            username="alice",
            password="secret",
        )

        assert proxy.url == "socks5://alice:secret@proxy.example:1080"

    def test_a_username_without_a_password(self) -> None:
        proxy = ProxyConfig(
            enabled=True, host="proxy.example", port=8080, username="alice"
        )

        assert proxy.url == "http://alice@proxy.example:8080"

    def test_credentials_are_percent_encoded(self) -> None:
        """An @ in the password would otherwise re-point the whole authority."""
        proxy = ProxyConfig(
            enabled=True,
            host="proxy.example",
            port=8080,
            username="al ice",
            password="p@ss:word/",
        )

        assert proxy.url == "http://al%20ice:p%40ss%3Aword%2F@proxy.example:8080"


class TestProxyFromDict:
    def test_a_missing_object_is_the_default(self) -> None:
        assert ProxyConfig.from_dict(None) == ProxyConfig()

    def test_an_unknown_scheme_falls_back_to_http(self) -> None:
        assert ProxyConfig.from_dict({"scheme": "gopher"}).scheme == "http"

    def test_a_nonsense_port_is_dropped(self) -> None:
        for port in ("8080", 0, -1, 99999, None):
            assert ProxyConfig.from_dict({"port": port}).port is None

    def test_a_real_port_survives(self) -> None:
        assert ProxyConfig.from_dict({"port": 1080}).port == 1080


class TestProviderConfigFromDict:
    def test_a_missing_object_keeps_the_default_model(self) -> None:
        stored = ProviderConfig.from_dict(None, provider=Provider.OPENROUTER)

        assert stored.model == Provider.OPENROUTER.default_model

    def test_an_unknown_thinking_level_falls_back_to_the_default(self) -> None:
        stored = ProviderConfig.from_dict(
            {"model": "vendor/model", "thinking": "ludicrous"},
            provider=Provider.OPENROUTER,
        )

        assert stored.thinking is Provider.OPENROUTER.default_thinking

    def test_a_stored_key_is_stripped(self) -> None:
        """A key with a stray newline would build an illegal header value."""
        stored = ProviderConfig.from_dict(
            {"api_key": " sk-x\n"}, provider=Provider.OPENROUTER
        )

        assert stored.api_key == "sk-x"

    def test_a_whitespace_only_key_reads_as_unset(self) -> None:
        stored = ProviderConfig.from_dict(
            {"api_key": "   "}, provider=Provider.OPENROUTER
        )

        assert stored.api_key == ""

    def test_a_blank_model_falls_back_to_the_default(self) -> None:
        stored = ProviderConfig.from_dict({"model": "  "}, provider=Provider.OPENAI)

        assert stored.model == Provider.OPENAI.default_model

    def test_the_default_model_keeps_what_it_is_known_to_support(self) -> None:
        """A file from before capabilities were recorded says nothing at all.

        Reading that silence as "cannot think" is what left a fresh install
        greying out the reasoning control for the model the app itself chose.
        """
        stored = ProviderConfig.from_dict(
            {"model": Provider.OPENROUTER.default_model},
            provider=Provider.OPENROUTER,
        )

        assert stored.model_supports_thinking is True

    def test_a_model_that_does_not_reason_says_so(self) -> None:
        stored = ProviderConfig.from_dict(
            {"model": "vendor/plain", "model_supports_thinking": False},
            provider=Provider.OPENAI,
        )

        assert stored.model_supports_thinking is False

    def test_a_superseded_default_is_replaced_by_the_current_one(self) -> None:
        """An old default was never a choice, so it must not outlive itself."""
        stale = next(iter(Provider.OPENROUTER.superseded_models))

        stored = ProviderConfig.from_dict(
            {"api_key": "sk-x", "model": stale, "thinking": "off"},
            provider=Provider.OPENROUTER,
        )

        assert stored.model == Provider.OPENROUTER.default_model
        assert stored.thinking is Provider.OPENROUTER.default_thinking
        assert stored.model_supports_thinking is True
        # The key is the user's, and it survives the model being replaced.
        assert stored.api_key == "sk-x"

    def test_a_model_the_user_picked_is_left_alone(self) -> None:
        stored = ProviderConfig.from_dict(
            {"model": "vendor/chosen", "thinking": "high"},
            provider=Provider.OPENROUTER,
        )

        assert stored.model == "vendor/chosen"
        assert stored.thinking is ThinkingLevel.HIGH

    def test_a_recorded_capability_is_believed_over_the_default(self) -> None:
        stored = ProviderConfig.from_dict(
            {
                "model": Provider.OPENROUTER.default_model,
                "model_supports_thinking": False,
            },
            provider=Provider.OPENROUTER,
        )

        assert stored.model_supports_thinking is False

    def test_another_model_is_not_given_the_defaults_capabilities(self) -> None:
        stored = ProviderConfig.from_dict(
            {"model": "vendor/something-else"}, provider=Provider.OPENROUTER
        )

        assert stored.model_supports_thinking is False


class TestAppConfig:
    def test_every_provider_starts_with_its_own_default_model(self) -> None:
        config = AppConfig()

        for provider in Provider:
            assert config.providers[provider].model == provider.default_model

    def test_active_follows_the_selected_provider(self) -> None:
        config = AppConfig(provider=Provider.GEMINI)

        assert config.active is config.providers[Provider.GEMINI]

    def test_active_is_created_when_a_provider_was_never_stored(self) -> None:
        config = AppConfig(provider=Provider.OPENAI, providers={})

        assert config.active.model == Provider.OPENAI.default_model

    def test_with_active_leaves_the_original_alone(self, config: AppConfig) -> None:
        updated = config.with_active(model="new/model")

        assert updated.active.model == "new/model"
        assert config.active.model == "vendor/model"

    def test_with_active_keeps_the_other_providers(self, config: AppConfig) -> None:
        """Switching provider must not cost the user the other keys."""
        updated = config.with_active(api_key="changed")

        assert updated.providers[Provider.GEMINI].api_key == "test-key"


class TestMissing:
    def test_a_ready_config_is_missing_nothing(self, config: AppConfig) -> None:
        assert config.missing() == []

    def test_a_missing_key_is_reported_by_provider_name(self) -> None:
        config = AppConfig()

        assert "OpenRouter API key" in config.missing()[0]

    def test_a_missing_model_is_reported(self, config: AppConfig) -> None:
        assert "No model selected" in config.with_active(model="").missing()

    def test_a_half_configured_proxy_is_reported(self, config: AppConfig) -> None:
        config.proxy = ProxyConfig(enabled=True)

        assert any("Proxy is enabled" in problem for problem in config.missing())

    def test_a_disabled_incomplete_proxy_is_not(self, config: AppConfig) -> None:
        config.proxy = ProxyConfig(enabled=False)

        assert config.missing() == []


class TestConfigStore:
    def test_a_missing_file_yields_the_defaults(
        self, config_store: ConfigStore
    ) -> None:
        assert config_store.load() == AppConfig()

    def test_a_round_trip_keeps_every_setting(
        self, config_store: ConfigStore, config: AppConfig
    ) -> None:
        config.provider = Provider.GEMINI
        config.proxy = ProxyConfig(
            enabled=True,
            scheme="socks5",
            host="proxy.example",
            port=1080,
            username="alice",
            password="secret",
        )
        config.show_rules = False
        config.theme = ThemeChoice.DARK
        config.temperature = 0.2
        config.max_tokens = 4096
        config.request_timeout = 45.0

        config_store.save(config)

        assert config_store.load() == config

    def test_saving_creates_the_directory(self, tmp_path: Path) -> None:
        store = ConfigStore(tmp_path / "nested" / "deeper" / "settings.json")

        store.save(AppConfig())

        assert store.path.is_file()

    def test_a_truncated_file_yields_the_defaults(
        self, config_store: ConfigStore
    ) -> None:
        """A write killed mid-flight must not stop the app from starting."""
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text('{"provider": "open', encoding="utf-8")

        assert config_store.load() == AppConfig()

    def test_a_file_holding_something_else_yields_the_defaults(
        self, config_store: ConfigStore
    ) -> None:
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text("[1, 2, 3]", encoding="utf-8")

        assert config_store.load() == AppConfig()

    def test_unknown_fields_are_ignored(self, config_store: ConfigStore) -> None:
        """A file from a newer version must still load."""
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text(
            json.dumps({"provider": "gemini", "future_setting": 7}),
            encoding="utf-8",
        )

        loaded = config_store.load()

        assert loaded.provider is Provider.GEMINI
        assert loaded.max_tokens == DEFAULT_MAX_TOKENS

    def test_nonsense_numbers_fall_back(self, config_store: ConfigStore) -> None:
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text(
            json.dumps({"temperature": "hot", "request_timeout": None}),
            encoding="utf-8",
        )

        loaded = config_store.load()

        assert loaded.request_timeout == DEFAULT_TIMEOUT
        assert loaded.temperature == AppConfig().temperature

    def test_an_unknown_theme_follows_the_system(
        self, config_store: ConfigStore
    ) -> None:
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text(json.dumps({"theme": "neon"}), encoding="utf-8")

        assert config_store.load().theme == ThemeChoice.SYSTEM

    def test_saving_leaves_no_temporary_files_behind(
        self, config_store: ConfigStore, config: AppConfig
    ) -> None:
        config_store.save(config)
        config_store.save(config)

        assert [path.name for path in config_store.path.parent.iterdir()] == [
            "settings.json"
        ]


class TestSaveFailure:
    def test_a_failed_write_leaves_no_temporary_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A phone that has run out of space must not leave litter behind."""
        store = ConfigStore(tmp_path / "settings.json")

        def full_disk(*_: object, **__: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "replace", full_disk)

        with pytest.raises(OSError, match="No space"):
            store.save(AppConfig())

        assert list(tmp_path.iterdir()) == []
