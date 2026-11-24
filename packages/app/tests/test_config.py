"""Tests for the settings model and the file it lives in."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from practice_core.providers import Provider

from practice_app.config import (
    DEFAULT_TIMEOUT,
    SETTINGS_VERSION,
    AppConfig,
    ConfigStore,
    ProviderConfig,
    ProxyConfig,
    ThemeChoice,
)


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


OPENROUTER = Provider.OPENROUTER
GEMINI = Provider.GEMINI


class TestAppConfig:
    def test_a_fresh_install_grades_through_google(self) -> None:
        """Google's free tier covers practice; OpenRouter has none."""
        config = AppConfig()

        assert config.provider is GEMINI
        assert config.active == ProviderConfig(model="gemini-decision-1")
        assert config.providers[OPENROUTER] == ProviderConfig(
            model="google/gemini-decision-1"
        )

    def test_active_follows_the_selected_provider(self, config: AppConfig) -> None:
        assert config.active.api_key == "test-key"
        assert replace(config, provider=GEMINI).active.api_key == "google-key"

    def test_active_falls_back_when_a_provider_was_never_stored(self) -> None:
        config = AppConfig(provider=GEMINI, providers={})

        assert config.active == ProviderConfig(model="gemini-decision-1")

    def test_with_active_changes_only_the_selected_provider(
        self, config: AppConfig
    ) -> None:
        """Switching provider must not cost the user the other key."""
        updated = config.with_active(api_key="changed")

        assert updated.active.api_key == "changed"
        assert updated.providers[GEMINI].api_key == "google-key"
        assert config.active.api_key == "test-key"

    def test_the_file_is_written_as_version_4(self, config: AppConfig) -> None:
        stored = config.to_dict()

        assert stored["version"] == SETTINGS_VERSION == 4
        assert stored["provider"] == "openrouter"
        assert stored["providers"] == {
            "openrouter": {"api_key": "test-key", "model": "gemini-decision-test"},
            "gemini": {"api_key": "google-key", "model": "gemini-decision-test"},
        }

    def test_a_version_4_file_round_trips(self, config: AppConfig) -> None:
        gemini = replace(config, provider=GEMINI)

        assert AppConfig.from_dict(gemini.to_dict()) == gemini

    def test_a_stored_key_is_stripped(self) -> None:
        """A key with a stray newline would build an illegal header value."""
        stored = AppConfig.from_dict(
            {"version": 4, "providers": {"gemini": {"api_key": " k\n"}}}
        )

        assert stored.active.api_key == "k"

    def test_a_blank_model_falls_back_to_the_providers_default(self) -> None:
        stored = AppConfig.from_dict(
            {
                "version": 4,
                "provider": "gemini",
                "providers": {"gemini": {"model": "  "}},
            }
        )

        assert stored.active.model == "gemini-decision-1"

    @pytest.mark.parametrize("provider", [None, "openai", 7])
    def test_an_unknown_provider_falls_back_to_google(self, provider: object) -> None:
        assert (
            AppConfig.from_dict({"version": 4, "provider": provider}).provider is GEMINI
        )


def _version_1(
    *, openrouter: dict[str, object], gemini: dict[str, object]
) -> dict[str, object]:
    """Return a settings file as version 1 of the app wrote it."""
    return {
        "version": 1,
        "provider": "openai",
        "providers": {
            "openrouter": openrouter,
            "gemini": {"thinking": "low", **gemini},
            "openai": {"api_key": "sk-oa", "model": "gpt-5.6-terra"},
        },
        "proxy": {"enabled": True, "host": "proxy.example", "port": 1080},
        "show_rules": False,
        "theme": "dark",
        "temperature": 0.2,
        "max_tokens": 4096,
        "request_timeout": 45.0,
    }


class TestMigrationFromVersion1:
    def test_each_key_goes_to_its_provider_stripped(self) -> None:
        migrated = AppConfig.from_dict(
            _version_1(
                openrouter={"api_key": " sk-or\n"}, gemini={"api_key": " AIza\n"}
            )
        )

        assert migrated.providers[OPENROUTER].api_key == "sk-or"
        assert migrated.providers[GEMINI].api_key == "AIza"
        assert migrated.provider is GEMINI

    def test_the_openai_key_has_nowhere_to_go(self) -> None:
        migrated = AppConfig.from_dict(_version_1(openrouter={}, gemini={}))

        assert "sk-oa" not in str(migrated.to_dict())

    def test_chat_models_are_replaced_by_each_providers_default(self) -> None:
        migrated = AppConfig.from_dict(
            _version_1(
                openrouter={"model": "google/gemini-3.8-flash"},
                gemini={"model": "gemini-3.8-flash"},
            )
        )

        assert migrated.providers[OPENROUTER].model == "google/gemini-decision-1"
        assert migrated.providers[GEMINI].model == "gemini-decision-1"

    def test_decision_models_are_kept(self) -> None:
        migrated = AppConfig.from_dict(
            _version_1(
                openrouter={"model": "microsoft/microsoft-decision-1.1"},
                gemini={"model": "gemini-decision-2"},
            )
        )

        assert (
            migrated.providers[OPENROUTER].model == "microsoft/microsoft-decision-1.1"
        )
        assert migrated.providers[GEMINI].model == "gemini-decision-2"

    def test_a_user_with_only_a_gemini_key_is_left_on_google(self) -> None:
        """Moving them to OpenRouter would strand a setup that works."""
        migrated = AppConfig.from_dict(
            _version_1(openrouter={"api_key": "  "}, gemini={"api_key": "AIza"})
        )

        assert migrated.provider is GEMINI

    def test_a_user_with_no_keys_starts_on_google(self) -> None:
        migrated = AppConfig.from_dict(_version_1(openrouter={}, gemini={}))

        assert migrated.provider is GEMINI

    def test_a_user_with_only_an_openrouter_key_stays_on_it(self) -> None:
        """Don't strand a working user on a provider with no key."""
        migrated = AppConfig.from_dict(
            _version_1(openrouter={"api_key": "sk-or"}, gemini={})
        )

        assert migrated.provider is OPENROUTER

    def test_the_rest_of_the_settings_survive(self) -> None:
        migrated = AppConfig.from_dict(
            _version_1(openrouter={"api_key": "k"}, gemini={})
        )

        assert migrated == AppConfig(
            provider=OPENROUTER,
            providers={
                OPENROUTER: ProviderConfig("k", "google/gemini-decision-1"),
                GEMINI: ProviderConfig("", "gemini-decision-1"),
            },
            proxy=ProxyConfig(enabled=True, host="proxy.example", port=1080),
            show_rules=False,
            theme=ThemeChoice.DARK,
            request_timeout=45.0,
        )

    @pytest.mark.parametrize(
        "providers", [None, "nonsense", {"gemini": "nonsense", "openrouter": 3}]
    )
    def test_a_mangled_provider_table_yields_the_defaults(
        self, providers: object
    ) -> None:
        migrated = AppConfig.from_dict({"version": 1, "providers": providers})

        assert migrated == AppConfig()


class TestMigrationFromVersion2:
    def test_the_google_key_and_model_move_to_the_google_provider(self) -> None:
        migrated = AppConfig.from_dict(
            {"version": 2, "api_key": " AIza\n", "model": "gemini-decision-2"}
        )

        assert migrated.providers[GEMINI] == ProviderConfig("AIza", "gemini-decision-2")
        assert migrated.providers[OPENROUTER] == ProviderConfig(
            "", "google/gemini-decision-1"
        )

    def test_a_working_google_setup_stays_on_google(self) -> None:
        migrated = AppConfig.from_dict({"version": 2, "api_key": "AIza"})

        assert migrated.provider is GEMINI
        assert migrated.missing() == []

    def test_no_key_stays_on_google(self) -> None:
        migrated = AppConfig.from_dict({"version": 2, "model": "gemini-decision-1"})

        assert migrated.provider is GEMINI

    def test_a_blank_model_becomes_the_default(self) -> None:
        migrated = AppConfig.from_dict({"version": 2, "api_key": "k", "model": ""})

        assert migrated.providers[GEMINI].model == "gemini-decision-1"

    def test_the_rest_of_the_settings_survive(self) -> None:
        migrated = AppConfig.from_dict(
            {"version": 2, "theme": "light", "show_rules": False, "request_timeout": 30}
        )

        assert migrated.theme is ThemeChoice.LIGHT
        assert migrated.show_rules is False
        assert migrated.request_timeout == 30.0

    def test_a_migrated_file_is_saved_as_version_4(
        self, config_store: ConfigStore
    ) -> None:
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text(
            json.dumps({"version": 2, "api_key": "k", "model": "gemini-decision-2"}),
            encoding="utf-8",
        )

        config_store.save(config_store.load())

        stored = json.loads(config_store.path.read_text(encoding="utf-8"))
        assert stored["version"] == 4
        assert stored["provider"] == "gemini"
        assert stored["providers"]["gemini"] == {
            "api_key": "k",
            "model": "gemini-decision-2",
        }
        assert "api_key" not in stored


class TestMigrationFromVersion3:
    """Version 3 called the providers "routes", and Gemini's one "google"."""

    @staticmethod
    def _stored(**changes: object) -> dict[str, object]:
        return {
            "version": 3,
            "route": "google",
            "routes": {
                "openrouter": {"api_key": "sk-or", "model": "microsoft/decision-1"},
                "google": {"api_key": "AIza", "model": "gemini-decision-2"},
            },
            "proxy": {"enabled": True, "host": "proxy.example", "port": 1080},
            "show_rules": False,
            "theme": "dark",
            "request_timeout": 45.0,
            **changes,
        }

    def test_a_google_route_becomes_gemini_with_its_key_and_model(self) -> None:
        migrated = AppConfig.from_dict(self._stored())

        assert migrated.provider is GEMINI
        assert migrated.providers[GEMINI] == ProviderConfig("AIza", "gemini-decision-2")
        assert migrated.missing() == []

    def test_an_openrouter_route_stays_on_openrouter(self) -> None:
        migrated = AppConfig.from_dict(self._stored(route="openrouter"))

        assert migrated.provider is OPENROUTER
        assert migrated.providers[OPENROUTER] == ProviderConfig(
            "sk-or", "microsoft/decision-1"
        )

    def test_the_rest_of_the_settings_survive(self) -> None:
        migrated = AppConfig.from_dict(self._stored())

        assert migrated.proxy == ProxyConfig(
            enabled=True, host="proxy.example", port=1080
        )
        assert migrated.show_rules is False
        assert migrated.theme is ThemeChoice.DARK
        assert migrated.request_timeout == 45.0

    @pytest.mark.parametrize("route", [None, "openai", 7])
    def test_an_unknown_route_falls_back_to_the_default(self, route: object) -> None:
        assert AppConfig.from_dict(self._stored(route=route)).provider is GEMINI

    @pytest.mark.parametrize("routes", [None, "nonsense", ["google"]])
    def test_a_mangled_route_table_yields_the_defaults(self, routes: object) -> None:
        migrated = AppConfig.from_dict(self._stored(route=None, routes=routes))

        assert migrated.providers == AppConfig().providers

    def test_an_unknown_route_is_dropped(self) -> None:
        stored = self._stored()
        stored["routes"] = {"google": {"api_key": "k"}, "bedrock": {"api_key": "leak"}}

        migrated = AppConfig.from_dict(stored)

        assert "leak" not in str(migrated.to_dict())
        assert migrated.providers[GEMINI].api_key == "k"

    def test_a_migrated_file_is_saved_as_version_4(
        self, config_store: ConfigStore
    ) -> None:
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text(json.dumps(self._stored()), encoding="utf-8")

        config_store.save(config_store.load())

        stored = json.loads(config_store.path.read_text(encoding="utf-8"))
        assert stored["version"] == 4
        assert stored["provider"] == "gemini"
        assert stored["providers"]["gemini"] == {
            "api_key": "AIza",
            "model": "gemini-decision-2",
        }
        assert "route" not in stored
        assert "routes" not in stored


class TestMissing:
    def test_a_ready_config_is_missing_nothing(self, config: AppConfig) -> None:
        assert config.missing() == []

    def test_a_missing_key_names_the_provider(self) -> None:
        assert AppConfig().missing() == ["Google AI Studio API key is not set"]
        assert AppConfig(provider=OPENROUTER).missing() == [
            "OpenRouter API key is not set"
        ]

    def test_a_missing_model_is_reported(self, config: AppConfig) -> None:
        assert config.with_active(model="").missing() == ["No model selected"]

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
        config_store.path.write_text('{"providers": {"open', encoding="utf-8")

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
            json.dumps(
                {
                    "version": 5,
                    "providers": {"gemini": {"api_key": "k"}, "bedrock": {}},
                    "future_setting": 7,
                }
            ),
            encoding="utf-8",
        )

        loaded = config_store.load()

        assert loaded.active.api_key == "k"
        assert loaded.active.model == "gemini-decision-1"

    def test_nonsense_numbers_fall_back(self, config_store: ConfigStore) -> None:
        config_store.path.parent.mkdir(parents=True, exist_ok=True)
        config_store.path.write_text(
            json.dumps({"request_timeout": "slow"}),
            encoding="utf-8",
        )

        assert config_store.load().request_timeout == DEFAULT_TIMEOUT

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
