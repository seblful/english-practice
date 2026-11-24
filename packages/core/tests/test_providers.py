"""Tests for the model providers."""

import pytest

from practice_core.providers import DEFAULT_PROVIDER, Provider


def test_gemini_is_the_default() -> None:
    """Google's free tier covers practice; OpenRouter has none."""
    assert DEFAULT_PROVIDER is Provider.GEMINI


@pytest.mark.parametrize(
    ("provider", "url", "model", "variable"),
    [
        (
            Provider.OPENROUTER,
            "https://openrouter.ai/api/alpha/decisions",
            "google/gemini-decision-1",
            "OPENROUTER_API_KEY",
        ),
        (
            Provider.GEMINI,
            "https://generativelanguage.googleapis.com/v1beta/decisions",
            "gemini-decision-1",
            "GEMINI_API_KEY",
        ),
    ],
)
def test_each_provider_knows_its_endpoint_model_and_key(
    provider: Provider, url: str, model: str, variable: str
) -> None:
    assert provider.decision_url == url
    assert provider.decision_model == model
    assert provider.key_variable == variable
    assert provider.label
    assert provider.key_url.startswith("https://")


def test_the_values_are_what_a_server_is_configured_with() -> None:
    """GRADER_PROVIDER and LLM_PROVIDER take these exact words."""
    assert [p.value for p in Provider] == ["gemini", "openrouter"]


def test_openrouter_takes_a_bearer_token() -> None:
    assert Provider.OPENROUTER.headers(" sk-or \n") == {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-or",
    }


def test_gemini_takes_googles_own_header() -> None:
    assert Provider.GEMINI.headers("g-key")["x-goog-api-key"] == "g-key"


@pytest.mark.parametrize("provider", list(Provider))
def test_no_key_sends_no_auth(provider: Provider) -> None:
    assert provider.headers("  ") == {"Content-Type": "application/json"}
