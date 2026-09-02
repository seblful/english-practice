"""Unit tests for application settings."""

from english_practice.settings import Settings


def test_settings_load_from_env_file(test_settings: Settings) -> None:
    """Nested settings are populated from the env file and defaults."""
    assert test_settings.app.environment == "test"
    assert test_settings.app.app_name == "english-practice"
    assert test_settings.app.secret_key is None
    assert test_settings.logging.console_level == "INFO"
