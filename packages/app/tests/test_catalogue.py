"""Tests for the decision-model catalogue and how a listing is read."""

from practice_core.providers import Provider

from practice_app.catalogue import (
    ModelInfo,
    default_model_info,
    is_decision_model,
    parse_models,
)

GEMINI = Provider.GEMINI
OPENROUTER = Provider.OPENROUTER


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

    def test_a_decision_model_takes_images_unless_told_otherwise(self) -> None:
        """Google's model page says so; the listing has no field that could."""
        assert ModelInfo(id="a", name="A").supports_images is True
        assert ModelInfo(id="a", name="A", supports_images=False).supports_images is (
            False
        )

    def test_search_narrows_across_terms(self) -> None:
        model = ModelInfo(id="gemini-decision-1", name="Gemini Decision 1")

        assert model.matches("gemini decision") is True
        assert model.matches("gemini flash") is False

    def test_search_reads_the_description_too(self) -> None:
        model = ModelInfo(id="a", name="B", description="Handles pictures")

        assert model.matches("pictures") is True

    def test_an_empty_search_matches_everything(self) -> None:
        assert ModelInfo(id="a", name="A").matches("   ") is True


class TestIsDecisionModel:
    def test_an_id_naming_a_decision_is_one(self) -> None:
        assert is_decision_model("gemini-decision-1") is True
        assert is_decision_model("Gemini-DECISION-2") is True

    def test_a_chat_model_is_not(self) -> None:
        assert is_decision_model("gemini-3.8-flash", ["generateContent"]) is False

    def test_a_decision_method_makes_one(self) -> None:
        """The listing's method name for decisions is undocumented, so any will do."""
        assert is_decision_model("gemini-judge", ["generateContent", "decide"]) is (
            False
        )
        assert is_decision_model("gemini-judge", ["createDecision"]) is True

    def test_a_method_that_is_not_a_string_is_ignored(self) -> None:
        assert is_decision_model("gemini-judge", [None, 7, {"decision": 1}]) is False


class TestGeminiListing:
    def test_only_decision_models_are_kept(self) -> None:
        payload = {
            "models": [
                {
                    "name": "models/gemini-3.8-flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-decision-1",
                    "displayName": "Gemini Decision 1",
                    "description": "Listed.",
                    "inputTokenLimit": 1_048_576,
                },
                {
                    "name": "models/gemini-judge",
                    "supportedGenerationMethods": ["createDecision"],
                },
            ]
        }

        models = parse_models(GEMINI, payload)

        assert [model.id for model in models] == ["gemini-decision-1", "gemini-judge"]
        assert models[0].description == "Listed."
        assert models[0].context_length == 1_048_576
        assert all(model.supports_images for model in models)

    def test_the_default_is_offered_when_the_listing_leaves_it_out(self) -> None:
        """Google does not document that decision models are listed at all."""
        assert parse_models(GEMINI, {"models": []}) == [default_model_info(GEMINI)]
        assert default_model_info(GEMINI).id == "gemini-decision-1"

    def test_the_default_comes_first(self) -> None:
        payload = {"models": [{"name": "models/gemini-decision-0"}]}

        assert [model.id for model in parse_models(GEMINI, payload)] == [
            "gemini-decision-1",
            "gemini-decision-0",
        ]

    def test_a_listed_default_replaces_the_built_in_entry(self) -> None:
        payload = {
            "models": [{"name": "models/gemini-decision-1", "displayName": "Listed"}]
        }

        models = parse_models(GEMINI, payload)

        assert len(models) == 1
        assert models[0].name == "Listed"

    def test_a_model_listed_twice_is_shown_once(self) -> None:
        payload = {
            "models": [
                {"name": "models/gemini-decision-2"},
                {"name": "gemini-decision-2"},
                {"name": "models/gemini-decision-1"},
                {"name": "models/gemini-decision-1"},
            ]
        }

        assert [model.id for model in parse_models(GEMINI, payload)] == [
            "gemini-decision-1",
            "gemini-decision-2",
        ]

    def test_a_display_name_falls_back_to_the_id(self) -> None:
        models = parse_models(
            GEMINI, {"models": [{"name": "models/gemini-decision-2"}]}
        )

        assert models[1].name == "gemini-decision-2"

    def test_malformed_entries_are_skipped(self) -> None:
        payload = {
            "models": [
                "nonsense",
                {"displayName": "No name"},
                {"name": "   "},
                {
                    "name": "models/gemini-decision-2",
                    "supportedGenerationMethods": "decide",
                    "inputTokenLimit": True,
                },
            ]
        }

        models = parse_models(GEMINI, payload)

        assert [model.id for model in models] == [
            "gemini-decision-1",
            "gemini-decision-2",
        ]
        assert models[1].context_length is None

    def test_a_reply_that_is_not_a_listing_still_offers_the_default(self) -> None:
        """A rewriting proxy can answer with anything."""
        assert parse_models(GEMINI, "a string") == [default_model_info(GEMINI)]
        assert parse_models(GEMINI, {"models": "none"}) == [default_model_info(GEMINI)]


def _openrouter(
    model_id: str,
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    **fields: object,
) -> dict[str, object]:
    """Return one entry shaped like OpenRouter's catalogue."""
    architecture: dict[str, object] = {}
    if inputs is not None:
        architecture["input_modalities"] = inputs
    if outputs is not None:
        architecture["output_modalities"] = outputs
    return {"id": model_id, "architecture": architecture, **fields}


class TestOpenRouterListing:
    def test_a_model_that_outputs_decisions_is_kept(self) -> None:
        payload = {
            "data": [
                _openrouter(
                    "jev/jev-1",
                    inputs=["text", "image"],
                    outputs=["decisions"],
                    name="Jev 1",
                    description="Judges.",
                    context_length=32_000,
                ),
                _openrouter("openai/gpt-5", inputs=["text"], outputs=["text"]),
            ]
        }

        models = parse_models(OPENROUTER, payload)

        assert [model.id for model in models] == [
            "google/gemini-decision-1",
            "jev/jev-1",
        ]
        assert models[1] == ModelInfo(
            id="jev/jev-1",
            name="Jev 1",
            description="Judges.",
            context_length=32_000,
            supports_images=True,
        )

    def test_an_id_naming_a_decision_is_kept_without_modalities(self) -> None:
        """The docs show no decision entry, so a bare one is not thrown away."""
        payload = {"data": [{"id": "microsoft/microsoft-decision-1.1"}]}

        models = parse_models(OPENROUTER, payload)

        assert models[1].id == "microsoft/microsoft-decision-1.1"
        assert models[1].name == "microsoft/microsoft-decision-1.1"

    def test_listed_input_modalities_decide_vision(self) -> None:
        payload = {
            "data": [
                _openrouter("a/png-only", inputs=["text"], outputs=["decisions"]),
                _openrouter("b/sees", inputs=["image"], outputs=["decisions"]),
            ]
        }

        vision = {
            model.id: model.supports_images
            for model in parse_models(OPENROUTER, payload)
        }

        assert vision["a/png-only"] is False
        assert vision["b/sees"] is True

    def test_without_modalities_only_gemini_decision_is_trusted_with_images(
        self,
    ) -> None:
        """Google documents image input for its model; nobody else's is assumed."""
        payload = {
            "data": [
                _openrouter("google/gemini-decision-2", outputs=["decisions"]),
                _openrouter("microsoft/microsoft-decision-1.1"),
            ]
        }

        vision = {
            model.id: model.supports_images
            for model in parse_models(OPENROUTER, payload)
        }

        assert vision["google/gemini-decision-2"] is True
        assert vision["microsoft/microsoft-decision-1.1"] is False

    def test_the_default_is_always_first_and_takes_images(self) -> None:
        assert parse_models(OPENROUTER, {"data": []}) == [
            default_model_info(OPENROUTER)
        ]
        assert default_model_info(OPENROUTER).id == "google/gemini-decision-1"
        assert default_model_info(OPENROUTER).supports_images is True

    def test_a_listed_default_keeps_its_details_but_takes_images(self) -> None:
        """An odd listing must not hide the model every exercise is graded on."""
        payload = {
            "data": [
                _openrouter(
                    "google/gemini-decision-1",
                    inputs=["text"],
                    outputs=["decisions"],
                    name="Google: Gemini Decision 1",
                ),
                _openrouter("google/gemini-decision-1", outputs=["decisions"]),
            ]
        }

        models = parse_models(OPENROUTER, payload)

        assert len(models) == 1
        assert models[0].name == "Google: Gemini Decision 1"
        assert models[0].supports_images is True

    def test_odd_payloads_still_offer_the_default(self) -> None:
        default = [default_model_info(OPENROUTER)]

        assert parse_models(OPENROUTER, None) == default
        assert parse_models(OPENROUTER, {"data": {"id": "x"}}) == default
        assert parse_models(OPENROUTER, {"models": [{"id": "a-decision"}]}) == default

    def test_malformed_entries_are_skipped(self) -> None:
        payload = {
            "data": [
                "nonsense",
                {"name": "No id"},
                {"id": "  "},
                {
                    "id": "x/decision-odd",
                    "architecture": "flat",
                    "context_length": "big",
                },
                {"id": "x/plain", "architecture": {"output_modalities": "decisions"}},
            ]
        }

        models = parse_models(OPENROUTER, payload)

        assert [model.id for model in models] == [
            "google/gemini-decision-1",
            "x/decision-odd",
        ]
        assert models[1].context_length is None
        assert models[1].supports_images is False
