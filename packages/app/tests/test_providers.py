"""Tests for the provider table and the thinking-level translation."""

import pytest

from practice_app.providers import (
    ModelInfo,
    Provider,
    ThinkingLevel,
    supported_thinking_levels,
    thinking_payload,
    thinking_token_headroom,
)


class TestProvider:
    @pytest.mark.parametrize("provider", list(Provider))
    def test_every_provider_is_fully_described(self, provider: Provider) -> None:
        """A provider without a label or a key page cannot be offered."""
        assert provider.label
        assert provider.console_url.startswith("https://")
        assert provider.default_model

    def test_only_openrouter_lists_models_without_a_key(self) -> None:
        assert Provider.OPENROUTER.lists_models_anonymously is True
        assert Provider.GEMINI.lists_models_anonymously is False
        assert Provider.OPENAI.lists_models_anonymously is False


class TestThinkingLevel:
    @pytest.mark.parametrize("level", list(ThinkingLevel))
    def test_every_level_is_fully_described(self, level: ThinkingLevel) -> None:
        assert level.label
        assert level.description


class TestSupportedThinkingLevels:
    def test_gemini_offers_auto(self) -> None:
        """Only Gemini has a budget that means "you decide"."""
        levels = supported_thinking_levels(Provider.GEMINI)

        assert ThinkingLevel.DYNAMIC in levels

    def test_the_effort_providers_do_not(self) -> None:
        for provider in (Provider.OPENROUTER, Provider.OPENAI):
            assert ThinkingLevel.DYNAMIC not in supported_thinking_levels(provider)

    @pytest.mark.parametrize("provider", list(Provider))
    def test_a_model_that_cannot_reason_gets_only_off(self, provider: Provider) -> None:
        """The control is then shown disabled rather than quietly removed."""
        assert supported_thinking_levels(provider, supports_thinking=False) == (
            ThinkingLevel.OFF,
        )

    @pytest.mark.parametrize("provider", list(Provider))
    def test_off_is_always_first(self, provider: Provider) -> None:
        assert supported_thinking_levels(provider)[0] is ThinkingLevel.OFF


class TestThinkingPayload:
    def test_gemini_sends_a_token_budget(self) -> None:
        payload = thinking_payload(Provider.GEMINI, ThinkingLevel.MEDIUM)

        assert payload == {"thinkingConfig": {"thinkingBudget": 8192}}

    def test_gemini_off_is_a_zero_budget(self) -> None:
        assert thinking_payload(Provider.GEMINI, ThinkingLevel.OFF) == {
            "thinkingConfig": {"thinkingBudget": 0}
        }

    def test_gemini_auto_is_a_negative_budget(self) -> None:
        assert thinking_payload(Provider.GEMINI, ThinkingLevel.DYNAMIC) == {
            "thinkingConfig": {"thinkingBudget": -1}
        }

    def test_openrouter_sends_a_nested_effort(self) -> None:
        payload = thinking_payload(Provider.OPENROUTER, ThinkingLevel.HIGH)

        assert payload == {"reasoning": {"effort": "high", "exclude": True}}

    def test_openrouter_off_disables_reasoning_explicitly(self) -> None:
        assert thinking_payload(Provider.OPENROUTER, ThinkingLevel.OFF) == {
            "reasoning": {"enabled": False}
        }

    def test_openai_sends_a_bare_effort(self) -> None:
        assert thinking_payload(Provider.OPENAI, ThinkingLevel.LOW) == {
            "reasoning_effort": "low"
        }

    def test_openai_off_is_the_none_effort(self) -> None:
        assert thinking_payload(Provider.OPENAI, ThinkingLevel.OFF) == {
            "reasoning_effort": "none"
        }

    @pytest.mark.parametrize("provider", list(Provider))
    def test_a_model_that_cannot_reason_is_sent_nothing(
        self, provider: Provider
    ) -> None:
        """Providers reject the parameter outright on a non-reasoning model."""
        assert (
            thinking_payload(provider, ThinkingLevel.HIGH, supports_thinking=False)
            == {}
        )


class TestThinkingTokenHeadroom:
    def test_off_needs_none(self) -> None:
        assert thinking_token_headroom(ThinkingLevel.OFF) == 0

    def test_headroom_grows_with_effort(self) -> None:
        ladder = [
            thinking_token_headroom(level)
            for level in (
                ThinkingLevel.OFF,
                ThinkingLevel.MINIMAL,
                ThinkingLevel.LOW,
                ThinkingLevel.MEDIUM,
                ThinkingLevel.HIGH,
            )
        ]

        assert ladder == sorted(ladder)
        assert ladder[0] < ladder[-1]

    def test_auto_gets_a_real_allowance(self) -> None:
        """Gemini's -1 budget is a signal, not a token count."""
        assert thinking_token_headroom(ThinkingLevel.DYNAMIC) > 0


class TestModelInfo:
    def test_context_in_millions(self) -> None:
        assert ModelInfo(id="a", name="A", context_length=2_097_152).context_label == (
            "2M context"
        )

    def test_context_in_thousands(self) -> None:
        assert ModelInfo(id="a", name="A", context_length=128_000).context_label == (
            "128K context"
        )

    def test_a_tiny_context(self) -> None:
        assert ModelInfo(id="a", name="A", context_length=512).context_label == (
            "512 context"
        )

    def test_an_unknown_context_says_nothing(self) -> None:
        assert ModelInfo(id="a", name="A").context_label == ""

    def test_prices_are_shown_per_million_tokens(self) -> None:
        model = ModelInfo(
            id="a", name="A", prompt_price=0.0000005, completion_price=0.0000015
        )

        assert model.price_label == "$0.50 / $1.50 per M"

    def test_a_free_model_says_so(self) -> None:
        model = ModelInfo(id="a", name="A", prompt_price=0.0, completion_price=0.0)

        assert model.price_label == "free"

    def test_an_unpriced_model_says_nothing(self) -> None:
        assert ModelInfo(id="a", name="A").price_label == ""

    def test_search_narrows_across_terms(self) -> None:
        model = ModelInfo(id="google/gemini-flash", name="Gemini Flash")

        assert model.matches("gemini flash") is True
        assert model.matches("gemini sonnet") is False

    def test_search_reads_the_description_too(self) -> None:
        model = ModelInfo(id="a/b", name="B", description="Handles pictures")

        assert model.matches("pictures") is True

    def test_an_empty_search_matches_everything(self) -> None:
        assert ModelInfo(id="a", name="A").matches("   ") is True
