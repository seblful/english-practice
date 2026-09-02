"""Tests for the screens.

These build real Flet controls against a page stand-in. Flet's controls are
validating dataclasses, so constructing the whole tree is itself the check that
every property and enum this app names actually exists — the failure mode these
tests exist to catch is a screen that raises the moment a phone opens it.

They also drive the flow: draw an exercise, answer it, see the verdict recorded.
"""

from dataclasses import replace
from typing import Any

import flet as ft
import httpx
import pytest
from practice_core.content import ContentLibrary

from practice_app.config import AppConfig, ConfigStore, ProxyConfig, ThemeChoice
from practice_app.providers import ModelInfo, Provider, ThinkingLevel
from practice_app.services import Services
from practice_app.stats import Attempt, StatsStore
from practice_app.ui.app import PRACTICE_TAB, SETTINGS_TAB, STATS_TAB, PracticeApp
from practice_app.ui.components import (
    banner,
    field_label,
    hint,
    panel,
    pill,
    placeholder,
    push,
    section_title,
    show_snack,
    stat_tile,
)
from practice_app.ui.model_picker import MAX_RESULTS, ModelPicker, visible_models
from practice_app.ui.practice_view import PracticeScreen
from practice_app.ui.settings_view import SettingsScreen
from practice_app.ui.stats_view import StatsScreen
from practice_app.ui.theme import build_theme, theme_mode
from tests.conftest import FakePage, reply_transport


def texts(control: Any) -> list[str]:
    """Return every string rendered anywhere under a control.

    Args:
        control: The control to walk.

    Returns:
        The text of each ``Text`` and ``Markdown``, and every button label.
    """
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        if not isinstance(node, ft.BaseControl):
            return
        if isinstance(node, (ft.Text, ft.Markdown)) and node.value:
            found.append(str(node.value))
        for attribute in ("content", "controls", "title", "label", "actions"):
            value = getattr(node, attribute, None)
            if isinstance(value, str):
                found.append(value)
            else:
                walk(value)

    walk(control)
    return found


def rendered(control: Any) -> str:
    """Return everything a control renders, joined for substring assertions."""
    return "\n".join(texts(control))


# ----------------------------------------------------------------------
# Theme and components
# ----------------------------------------------------------------------


class TestTheme:
    def test_the_theme_is_buildable(self) -> None:
        theme = build_theme()

        assert theme.use_material3 is True
        assert theme.color_scheme_seed

    @pytest.mark.parametrize(
        ("choice", "expected"),
        [
            (ThemeChoice.SYSTEM, ft.ThemeMode.SYSTEM),
            (ThemeChoice.LIGHT, ft.ThemeMode.LIGHT),
            (ThemeChoice.DARK, ft.ThemeMode.DARK),
            ("nonsense", ft.ThemeMode.SYSTEM),
        ],
    )
    def test_the_stored_choice_maps_to_a_mode(
        self, choice: str, expected: ft.ThemeMode
    ) -> None:
        assert theme_mode(choice) is expected


class TestComponents:
    def test_a_panel_can_carry_a_title(self) -> None:
        built = panel(ft.Text("body"), title="Section")

        assert "SECTION" in rendered(built)
        assert "body" in rendered(built)

    def test_a_pill_with_an_icon(self) -> None:
        built = pill("Topic", icon=ft.Icons.CATEGORY_ROUNDED)

        assert "Topic" in rendered(built)

    def test_a_banner_shows_its_actions(self) -> None:
        built = banner(
            "Something is missing",
            icon=ft.Icons.WARNING_AMBER_ROUNDED,
            color=ft.Colors.ON_ERROR_CONTAINER,
            bgcolor=ft.Colors.ERROR_CONTAINER,
            actions=[ft.TextButton(content="Fix it")],
        )

        assert "Something is missing" in rendered(built)
        assert "Fix it" in rendered(built)

    def test_a_placeholder_shows_its_message(self) -> None:
        built = placeholder(
            icon=ft.Icons.SCHOOL_ROUNDED, title="Nothing here", message="Try this"
        )

        assert "Nothing here" in rendered(built)
        assert "Try this" in rendered(built)

    def test_the_small_pieces_build(self) -> None:
        assert hint("a").value == "a"
        assert field_label("b").value == "b"
        assert section_title("c").value == "C"
        assert "7" in rendered(stat_tile("7", "streak", ft.Icons.BOLT_ROUNDED))

    def test_a_snack_bar_reaches_the_page(self, page: FakePage) -> None:
        show_snack(page, "saved")

        assert page.snack_texts() == ["saved"]

    def test_an_error_snack_bar_is_coloured(self, page: FakePage) -> None:
        show_snack(page, "failed", error=True)

        assert page.last_dialog.bgcolor == ft.Colors.ERROR_CONTAINER

    def test_pushing_an_unattached_control_is_harmless(self) -> None:
        """The shell refreshes a tab before it has ever been on screen."""
        push(ft.Column(controls=[ft.Text("x")]))


# ----------------------------------------------------------------------
# Practice screen
# ----------------------------------------------------------------------


class TestPracticeScreenStart:
    def test_a_configured_app_starts_with_the_topic_choices(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        body = rendered(screen)
        assert "Ready to practise?" in body
        assert "Random exercise" in body
        assert "Choose a topic" in body

    def test_an_unconfigured_app_says_what_is_missing(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = AppConfig()
        opened: list[bool] = []
        screen = PracticeScreen(
            page, services, on_open_settings=lambda: opened.append(True)
        )

        body = rendered(screen)
        assert "API key is not set" in body
        assert "Open settings" in body

    def test_the_setup_banner_can_reach_the_settings_tab(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = AppConfig()
        opened: list[bool] = []
        screen = PracticeScreen(
            page, services, on_open_settings=lambda: opened.append(True)
        )

        banner_control = screen.controls[0]
        button = _find(banner_control, ft.FilledButton)
        button.on_click(None)

        assert opened == [True]

    def test_without_a_settings_hook_the_banner_has_no_button(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = AppConfig()
        screen = PracticeScreen(page, services)

        assert _find_or_none(screen.controls[0], ft.FilledButton) is None


def _find(control: Any, kind: type) -> Any:
    """Return the first control of a type under ``control``.

    Args:
        control: Where to start.
        kind: The control class to look for.

    Returns:
        The control.

    Raises:
        AssertionError: If nothing of that type is present.
    """
    found = _find_or_none(control, kind)
    assert found is not None, f"no {kind.__name__} found"
    return found


def _find_or_none(control: Any, kind: type) -> Any:
    """Return the first control of a type under ``control``, or ``None``."""
    if isinstance(control, kind):
        return control
    if isinstance(control, (list, tuple)):
        for item in control:
            found = _find_or_none(item, kind)
            if found is not None:
                return found
        return None
    if not isinstance(control, ft.BaseControl):
        return None
    for attribute in ("content", "controls", "title", "label", "actions"):
        found = _find_or_none(getattr(control, attribute, None), kind)
        if found is not None:
            return found
    return None


def _all(control: Any, kind: type) -> list[Any]:
    """Return every control of a type under ``control``."""
    found: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, kind):
            found.append(node)
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        if not isinstance(node, ft.BaseControl):
            return
        for attribute in ("content", "controls", "title", "label", "actions"):
            walk(getattr(node, attribute, None))

    walk(control)
    return found


class TestPracticeScreenFlow:
    async def test_drawing_puts_an_exercise_on_screen(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.draw(1, "Present Tenses")

        body = rendered(screen)
        assert "Present Tenses" in body
        assert "Question 2" in body
        assert "Unit 1" in body
        assert "Check answer" in body

    async def test_the_exercise_image_is_shown(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.draw(1, "Present Tenses")

        assert _find(screen, ft.Image).src == b"\x89PNG\r\n\x1a\n"

    async def test_an_exercise_without_a_picture_says_so(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.draw(2, "Past Tenses")

        assert "no picture" in rendered(screen)

    async def test_an_empty_topic_is_reported(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.draw(999, "Nothing")

        assert "No exercises found" in page.snack_texts()[0]

    async def test_answering_shows_the_verdict_and_the_book_answer(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "is doing"

        await screen._on_check()

        body = rendered(screen)
        assert "CORRECT ANSWER" in body
        assert "is doing" in body
        assert "FULL ANSWER" in body
        assert "Next exercise" in body

    async def test_a_graded_answer_is_recorded(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "is doing"

        await screen._on_check()

        summary = await services.stats.summary()
        assert summary.total == 1
        assert summary.correct == 1

    async def test_the_rule_is_shown_when_enabled(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "is doing"

        await screen._on_check()

        assert "Use present continuous" in rendered(screen)

    async def test_the_rule_is_hidden_when_disabled(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = replace(services.config, show_rules=False)
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "is doing"

        await screen._on_check()

        assert "Use present continuous" not in rendered(screen)

    async def test_an_empty_answer_is_refused(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "   "

        await screen._on_check()

        assert "Type your answer first" in page.snack_texts()[0]

    async def test_a_failed_grading_still_reveals_the_answer(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        """The student is not left staring at a question with no answer."""
        broken = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(lambda _: httpx.Response(500, json={})),
        )
        broken.client._sleep = _instant
        screen = PracticeScreen(page, broken)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "is doing"

        await screen._on_check()

        assert "Could not grade that" in page.snack_texts()[0]
        assert "CORRECT ANSWER" in rendered(screen)

    async def test_a_failed_grading_is_not_counted(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        broken = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(lambda _: httpx.Response(401, json={})),
        )
        screen = PracticeScreen(page, broken)
        await screen.draw(1, "Present Tenses")
        screen._answer.value = "is doing"

        await screen._on_check()

        assert (await stats.summary()).total == 0

    async def test_revealing_skips_the_model_entirely(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")

        await screen._on_reveal()

        assert "CORRECT ANSWER" in rendered(screen)
        assert (await services.stats.summary()).total == 0

    async def test_next_draws_from_the_same_topic(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")

        await screen._on_next()

        assert screen._session.active is not None
        assert screen._session.active.topic_id == 1

    async def test_random_labels_the_topic_it_landed_on(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen._on_random()

        assert screen._session.active is not None
        assert screen._session.active.topic_id is None
        assert screen._session.active.topic_name in {
            "Present Tenses",
            "Past Tenses",
        }

    async def test_the_same_topic_button_appears_after_a_topic_draw(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._session.clear()
        screen.render()

        assert "Again: Present Tenses" in rendered(screen)

    async def test_the_same_topic_button_redraws_that_topic(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")

        await screen._on_same_topic()

        assert screen._session.active is not None
        assert screen._session.active.topic_id == 1

    async def test_the_topic_chooser_lists_the_topics(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen._on_choose_topic()

        body = rendered(page.last_dialog)
        assert "Present Tenses" in body
        assert "Past Tenses" in body
        assert "1 unit" in body

    async def test_choosing_a_topic_closes_the_dialog_and_draws(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen._on_choose_topic()
        topics = await services.content.list_topics()

        await screen._pick_topic(topics[1])

        assert page.popped == 1
        assert screen._session.active is not None
        assert screen._session.active.topic_name == topics[1].name

    async def test_the_unit_dialog_names_the_unit(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")

        active = screen._session.active
        assert active is not None
        screen._show_unit(active)

        assert "Present Continuous" in rendered(page.last_dialog)

    async def test_the_image_can_be_zoomed(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")

        active = screen._session.active
        assert active is not None
        screen._zoom_image(active)

        assert _find(page.last_dialog, ft.InteractiveViewer) is not None

    async def test_a_busy_screen_shows_progress(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.draw(1, "Present Tenses")
        screen._busy = True
        screen.render()

        assert "Grading your answer" in rendered(screen)

    async def test_an_open_question_says_the_book_prints_no_answer(
        self, page: FakePage, services: Services
    ) -> None:
        """Showing a canonical answer to a free-form question would mislead."""
        screen = PracticeScreen(page, services)
        await screen.draw(2, "Past Tenses")

        await screen._on_reveal()

        body = rendered(screen)
        assert "open-ended" in body
        assert "FULL ANSWER" not in body

    async def test_a_broken_content_database_is_reported(
        self,
        page: FakePage,
        config_store: ConfigStore,
        stats: StatsStore,
        config: AppConfig,
        tmp_path: Any,
    ) -> None:
        """The exercises ship with the app, so this is a reinstall, not a retry."""
        missing = Services(
            config_store=config_store,
            content=ContentLibrary(tmp_path / "absent.db", read_only=True),
            stats=stats,
            config=config,
        )
        screen = PracticeScreen(page, missing)

        await screen.draw(1, "Present Tenses")
        await screen._on_choose_topic()

        assert "database is missing" in page.snack_texts()[0]
        assert "database is missing" in page.snack_texts()[1]

    def test_refreshing_redraws(self, page: FakePage, services: Services) -> None:
        screen = PracticeScreen(page, services)
        services.config = AppConfig()

        screen.refresh()

        assert "API key is not set" in rendered(screen)


async def _instant(_: float) -> None:
    """Skip the retry delay."""


# ----------------------------------------------------------------------
# Stats screen
# ----------------------------------------------------------------------


class TestStatsScreen:
    async def test_an_empty_history_says_where_to_start(
        self, page: FakePage, services: Services
    ) -> None:
        screen = StatsScreen(page, services)

        await screen.refresh()

        assert "No progress yet" in rendered(screen)

    async def test_the_figures_reach_the_screen(
        self, page: FakePage, services: Services
    ) -> None:
        for correct in (True, True, False):
            await services.stats.record(
                Attempt(
                    topic_name="Present Tenses",
                    unit_number=1,
                    exercise_id="1.1",
                    question_id="2",
                    is_correct=correct,
                )
            )
        screen = StatsScreen(page, services)

        await screen.refresh()

        body = rendered(screen)
        assert "67%" in body
        assert "2 correct" in body
        assert "1 to revisit" in body
        assert "Present Tenses" in body
        assert "LAST 7 DAYS" in body

    async def test_resetting_asks_first(
        self, page: FakePage, services: Services
    ) -> None:
        await services.stats.record(
            Attempt(
                topic_name="T",
                unit_number=1,
                exercise_id="1.1",
                question_id="1",
                is_correct=True,
            )
        )
        screen = StatsScreen(page, services)
        await screen.refresh()

        screen._confirm_reset()

        assert "cannot be undone" in rendered(page.last_dialog)

    async def test_confirming_the_reset_clears_the_history(
        self, page: FakePage, services: Services
    ) -> None:
        await services.stats.record(
            Attempt(
                topic_name="T",
                unit_number=1,
                exercise_id="1.1",
                question_id="1",
                is_correct=True,
            )
        )
        screen = StatsScreen(page, services)
        await screen.refresh()

        await screen._reset()

        assert (await services.stats.summary()).is_empty is True
        assert "Progress reset." in page.snack_texts()
        assert "No progress yet" in rendered(screen)

    async def test_many_topics_are_summarised(
        self, page: FakePage, services: Services
    ) -> None:
        for index in range(12):
            await services.stats.record(
                Attempt(
                    topic_name=f"Topic {index:02d}",
                    unit_number=1,
                    exercise_id="1.1",
                    question_id="1",
                    is_correct=index % 2 == 0,
                )
            )
        screen = StatsScreen(page, services)

        await screen.refresh()

        assert "more topics" in rendered(screen)


# ----------------------------------------------------------------------
# Model picker
# ----------------------------------------------------------------------


class TestVisibleModels:
    def test_no_filters_shows_everything(self, catalogue: list[ModelInfo]) -> None:
        assert visible_models(catalogue, "") == catalogue

    def test_the_search_narrows(self, catalogue: list[ModelInfo]) -> None:
        assert [m.id for m in visible_models(catalogue, "vendor")] == [
            "vendor/model",
            "vendor/text-only",
        ]

    def test_vision_only(self, catalogue: list[ModelInfo]) -> None:
        assert [m.id for m in visible_models(catalogue, "", vision_only=True)] == [
            "vendor/model"
        ]

    def test_thinking_only(self, catalogue: list[ModelInfo]) -> None:
        assert [m.id for m in visible_models(catalogue, "", thinking_only=True)] == [
            "vendor/model",
            "other/thinker",
        ]

    def test_free_only(self, catalogue: list[ModelInfo]) -> None:
        assert [m.id for m in visible_models(catalogue, "", free_only=True)] == [
            "vendor/text-only"
        ]

    def test_filters_combine(self, catalogue: list[ModelInfo]) -> None:
        assert visible_models(catalogue, "", vision_only=True, free_only=True) == []


class TestModelPicker:
    def _picker(
        self, catalogue: list[ModelInfo], selected: str = "vendor/model"
    ) -> tuple[ModelPicker, list[ModelInfo], list[int]]:
        """Return a picker and the lists its callbacks append to."""
        picked: list[ModelInfo] = []
        refreshed: list[int] = []
        picker = ModelPicker(
            provider_label="OpenRouter",
            models=catalogue,
            selected=selected,
            on_select=picked.append,
            on_refresh=lambda: refreshed.append(1),
        )
        return picker, picked, refreshed

    def test_it_lists_the_catalogue_with_badges(
        self, catalogue: list[ModelInfo]
    ) -> None:
        picker, _, _ = self._picker(catalogue)

        body = rendered(picker)
        assert "Vendor Model" in body
        assert "vision" in body
        assert "thinking" in body
        assert "1M context" in body

    def test_the_vision_filter_starts_on_when_the_data_supports_it(
        self, catalogue: list[ModelInfo]
    ) -> None:
        picker, _, _ = self._picker(catalogue)

        assert picker._vision.selected is True

    def test_searching_narrows_the_list(self, catalogue: list[ModelInfo]) -> None:
        picker, _, _ = self._picker(catalogue)
        picker._vision.selected = False
        picker._search.value = "thinker"

        picker._refilter()

        assert "Other Thinker" in rendered(picker)
        assert "Vendor Text" not in rendered(picker)

    def test_a_search_with_no_matches_says_so(self, catalogue: list[ModelInfo]) -> None:
        picker, _, _ = self._picker(catalogue)
        picker._search.value = "nothing like this"

        picker._refilter()

        assert "No model matches" in rendered(picker)

    def test_a_long_catalogue_is_capped(self) -> None:
        """Building five hundred rows per keystroke is what feels broken."""
        many = [
            ModelInfo(id=f"vendor/model-{index:03d}", name=f"Model {index}")
            for index in range(MAX_RESULTS + 20)
        ]
        picker = ModelPicker(
            provider_label="OpenRouter",
            models=many,
            selected="",
            on_select=lambda _: None,
            on_refresh=lambda: None,
        )

        assert "more match" in rendered(picker)
        assert len(picker._list.controls) == MAX_RESULTS + 1

    def test_picking_reports_the_model(self, catalogue: list[ModelInfo]) -> None:
        picker, picked, _ = self._picker(catalogue)

        picker._pick(catalogue[1])

        assert picked == [catalogue[1]]

    def test_refreshing_is_reported(self, catalogue: list[ModelInfo]) -> None:
        picker, _, refreshed = self._picker(catalogue)

        _find(picker.title, ft.IconButton).on_click(None)

        assert refreshed == [1]

    def test_the_count_reflects_the_filters(self, catalogue: list[ModelInfo]) -> None:
        picker, _, _ = self._picker(catalogue)

        assert "1 of 3 models" in str(picker._count.value)


# ----------------------------------------------------------------------
# Settings screen
# ----------------------------------------------------------------------


class TestSettingsScreen:
    async def test_it_shows_every_section(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen.refresh()

        body = rendered(screen)
        for section in ("PROVIDER", "MODEL", "REASONING", "PROXY", "PRACTICE"):
            assert section in body

    async def test_the_about_section_counts_the_book(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen.refresh()

        assert "2 exercises and 2 questions" in rendered(screen)

    def test_the_selected_provider_and_model_are_shown(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        body = rendered(screen)
        assert "OpenRouter" in body
        assert "vendor/model" in body

    async def test_switching_provider_keeps_the_other_keys(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_provider(_event(_segmented("gemini")))

        assert services.config.provider is Provider.GEMINI
        assert services.config.providers[Provider.OPENROUTER].api_key == "test-key"

    async def test_the_api_key_is_staged_then_written_on_blur(
        self, page: FakePage, services: Services
    ) -> None:
        """A write per keystroke would rebuild the pool under the user's finger."""
        screen = SettingsScreen(page, services)
        field = ft.TextField(value="new-key")

        screen._stage_api_key(_event(field))
        assert services.config_store.load().active.api_key == ""

        await screen._commit_api_key()
        assert services.config_store.load().active.api_key == "new-key"

    async def test_the_thinking_level_is_saved(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = services.config.with_active(model_supports_thinking=True)
        screen = SettingsScreen(page, services)

        await screen._on_thinking(_event(ft.Dropdown(value="high")))

        assert services.config.active.thinking is ThinkingLevel.HIGH

    def test_a_model_that_cannot_think_disables_the_control(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        assert "no thinking control" in rendered(screen)
        assert _find(screen.controls[2], ft.Dropdown).disabled is True

    async def test_choosing_a_model_carries_its_capabilities(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        """The request builder needs both, and a restart must not re-fetch."""
        screen = SettingsScreen(page, services)

        await screen._choose_model(catalogue[0])

        active = services.config_store.load().active
        assert active.model == "vendor/model"
        assert active.model_supports_thinking is True
        assert active.model_supports_json is True

    async def test_choosing_a_model_that_cannot_think_resets_the_level(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        services.config = services.config.with_active(
            model_supports_thinking=True, thinking=ThinkingLevel.HIGH
        )
        screen = SettingsScreen(page, services)

        await screen._choose_model(catalogue[1])

        assert services.config.active.thinking is ThinkingLevel.OFF

    async def test_a_model_without_vision_is_flagged(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        """Every exercise is a picture, so this is the common misconfiguration."""
        screen = SettingsScreen(page, services)
        services._catalogues[Provider.OPENROUTER] = catalogue
        await screen._choose_model(catalogue[2])

        assert "does not accept images" in rendered(screen)

    async def test_the_proxy_fields_appear_once_it_is_enabled(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)
        assert "Host" not in rendered(screen)

        await screen._on_proxy_enabled(_event(ft.Switch(value=True)))

        body = rendered(screen)
        assert "Host" in body
        assert "Port" in body
        assert "Username (optional)" in body

    async def test_an_incomplete_proxy_is_flagged(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_proxy_enabled(_event(ft.Switch(value=True)))

        assert "Add a host and a port" in rendered(screen)

    async def test_the_proxy_fields_are_staged_and_committed(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = replace(services.config, proxy=ProxyConfig(enabled=True))
        screen = SettingsScreen(page, services)

        screen._stage_proxy_host(_event(ft.TextField(value="proxy.example")))
        screen._stage_proxy_port(_event(ft.TextField(value="8080")))
        screen._stage_proxy_username(_event(ft.TextField(value="alice")))
        screen._stage_proxy_password(_event(ft.TextField(value="secret")))
        await screen._commit()

        stored = services.config_store.load().proxy
        assert stored.url == "http://alice:secret@proxy.example:8080"

    async def test_a_nonsense_port_is_dropped(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = replace(services.config, proxy=ProxyConfig(enabled=True))
        screen = SettingsScreen(page, services)

        screen._stage_proxy_port(_event(ft.TextField(value="0")))

        assert services.config.proxy.port is None

    async def test_the_proxy_scheme_is_saved(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = replace(services.config, proxy=ProxyConfig(enabled=True))
        screen = SettingsScreen(page, services)

        await screen._on_proxy_scheme(_event(ft.Dropdown(value="socks5")))

        assert services.config.proxy.scheme == "socks5"

    async def test_the_advanced_numbers_are_clamped(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        screen._stage_max_tokens(_event(ft.TextField(value="99999999")))
        screen._stage_timeout(_event(ft.TextField(value="1")))
        await screen._commit()

        stored = services.config_store.load()
        assert stored.max_tokens <= 32768
        assert stored.request_timeout >= 10.0

    async def test_unparsable_numbers_fall_back(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        screen._stage_max_tokens(_event(ft.TextField(value="")))
        screen._stage_timeout(_event(ft.TextField(value="")))

        assert services.config.max_tokens == 2048
        assert services.config.request_timeout == 90.0

    async def test_the_temperature_is_saved(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_temperature(_event(ft.Slider(value=0.25)))

        assert services.config.temperature == 0.25

    async def test_a_slider_without_a_value_changes_nothing(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_temperature(_event(ft.Slider(value=None)))

        assert services.config.temperature == 0.7

    async def test_the_rule_toggle_is_saved(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_show_rules(_event(ft.Switch(value=False)))

        assert services.config_store.load().show_rules is False

    async def test_the_theme_is_saved(self, page: FakePage, services: Services) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_theme(_event(_segmented("dark")))

        assert services.config_store.load().theme == ThemeChoice.DARK

    async def test_the_key_page_can_be_opened(
        self, page: FakePage, services: Services
    ) -> None:
        """The real `launch_url` is a coroutine, so it has to be awaited."""
        screen = SettingsScreen(page, services)

        await _find(screen.controls[0], ft.TextButton).on_click()

        assert page.launched == [Provider.OPENROUTER.console_url]

    async def test_a_successful_connection_test_is_reported(
        self, page: FakePage, services: Services
    ) -> None:
        services._client = None
        services._transport = reply_transport('{"ok": true}')
        screen = SettingsScreen(page, services)

        await screen._on_check()

        assert "answered as vendor/model" in rendered(screen)

    async def test_a_failed_connection_test_is_reported(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        broken = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(lambda _: httpx.Response(401, json={})),
        )
        screen = SettingsScreen(page, broken)

        await screen._on_check()

        assert "rejected the API key" in rendered(screen)

    async def test_opening_the_picker_fetches_the_catalogue(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        listed = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": [{"id": "vendor/model"}]})
            ),
        )
        screen = SettingsScreen(page, listed)

        await screen._on_open_models()

        assert isinstance(page.last_dialog, ModelPicker)

    async def test_a_catalogue_that_cannot_be_fetched_is_reported(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        broken = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(lambda _: httpx.Response(401, json={})),
        )
        screen = SettingsScreen(page, broken)

        await screen._on_open_models()

        assert "rejected the API key" in page.snack_texts()[0]

    async def test_reloading_the_catalogue_reopens_the_picker(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        listed = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": [{"id": "vendor/model"}]})
            ),
        )
        screen = SettingsScreen(page, listed)

        await screen._reload_models()

        assert page.popped == 1
        assert isinstance(page.last_dialog, ModelPicker)

    def test_the_pickers_callbacks_schedule_work(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        screen = SettingsScreen(page, services)

        screen._schedule_choose_model(catalogue[0])
        screen._schedule_reload_models()

        assert len(page.tasks) == 2


def _segmented(value: str) -> ft.SegmentedButton:
    """Return a segmented button reporting one selected value.

    Args:
        value: The value the user chose.

    Returns:
        The control, with the single segment Flet requires.
    """
    return ft.SegmentedButton(
        segments=[ft.Segment(value=value, label=ft.Text(value))],
        selected=[value],
    )


def _event(control: Any) -> Any:
    """Return something shaped like a Flet event for one control.

    Args:
        control: The control the event came from.

    Returns:
        An object exposing ``control``.
    """
    return type("Event", (), {"control": control})()


# ----------------------------------------------------------------------
# The shell
# ----------------------------------------------------------------------


class TestPracticeApp:
    async def test_starting_builds_the_page(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)

        await app.start()

        assert page.title == "English Practice"
        assert page.theme is not None
        assert page.dark_theme is not None
        assert page.appbar is not None
        assert page.navigation_bar is not None
        assert len(page.navigation_bar.destinations) == 3
        assert page.controls

    async def test_each_tab_shows_its_screen(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        for index, screen in (
            (STATS_TAB, app.stats),
            (SETTINGS_TAB, app.settings),
            (PRACTICE_TAB, app.practice),
        ):
            await app.select_tab(index)

            assert app._body.content is screen
            assert page.navigation_bar.selected_index == index

    async def test_the_tab_title_follows_the_tab(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        await app.select_tab(STATS_TAB)

        assert page.appbar.title.value == "Progress"

    async def test_switching_tabs_keeps_the_open_exercise(
        self, page: FakePage, services: Services
    ) -> None:
        """Losing a half-answered exercise would be the app's worst bug."""
        app = PracticeApp(page, services)
        await app.start()
        await app.practice.draw(1, "Present Tenses")

        await app.select_tab(STATS_TAB)
        await app.select_tab(PRACTICE_TAB)

        assert app.practice._session.active is not None

    async def test_the_navigation_bar_switches_tabs(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        await page.navigation_bar.on_change(
            _event(ft.NavigationBar(selected_index=SETTINGS_TAB, destinations=[]))
        )

        assert app._body.content is app.settings

    async def test_the_theme_button_cycles(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        await app._cycle_theme()
        assert services.config.theme == ThemeChoice.LIGHT
        assert page.theme_mode is ft.ThemeMode.LIGHT

        await app._cycle_theme()
        assert services.config.theme == ThemeChoice.DARK

        await app._cycle_theme()
        assert services.config.theme == ThemeChoice.SYSTEM

    async def test_a_saved_setting_reaches_the_practice_tab(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()
        services.config = AppConfig()

        app._settings_changed()

        assert "API key is not set" in rendered(app.practice)

    async def test_the_setup_banner_jumps_to_the_settings_tab(
        self, page: FakePage, services: Services
    ) -> None:
        services.config = AppConfig()
        app = PracticeApp(page, services)
        await app.start()

        app._open_settings()
        await page.drain()

        assert app._body.content is app.settings
