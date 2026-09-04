"""Tests for the screens.

These build real Flet controls against a page stand-in. Flet's controls are
validating dataclasses, so constructing the whole tree is itself the check that
every property and enum this app names actually exists — the failure mode these
tests exist to catch is a screen that raises the moment a phone opens it.

They also drive the flow: draw an exercise, answer it, see the verdict recorded.
"""

from dataclasses import replace
from datetime import date
from typing import Any, cast

import flet as ft
import httpx
import pytest
from practice_core.content import ContentLibrary
from practice_core.models import Topic

from practice_app.config import AppConfig, ConfigStore, ProxyConfig, ThemeChoice
from practice_app.providers import (
    ModelInfo,
    Provider,
    ThinkingLevel,
    supported_thinking_levels,
)
from practice_app.services import Services
from practice_app.session import Lesson
from practice_app.stats import Attempt, DayStat, StatsStore, StatsSummary, TopicStat
from practice_app.ui import motion
from practice_app.ui.app import PRACTICE_TAB, SETTINGS_TAB, STATS_TAB, PracticeApp
from practice_app.ui.components import (
    SEGMENT_LABEL_SIZE,
    action_bar,
    banner,
    field_label,
    hint,
    panel,
    pill,
    placeholder,
    primary_action,
    progress_track,
    push,
    secondary_action,
    section_title,
    sheet,
    show_snack,
    stat_tile,
    switch_row,
)
from practice_app.ui.home_view import MIXED_LESSON_LABEL, HomeState, HomeView
from practice_app.ui.model_picker import MAX_RESULTS, ModelPicker, visible_models
from practice_app.ui.practice_view import PracticeScreen
from practice_app.ui.screen import Screen
from practice_app.ui.settings_view import SettingsScreen
from practice_app.ui.stats_view import StatsScreen
from practice_app.ui.theme import CORRECT, ON_CORRECT, build_theme, theme_mode
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
        for attribute in (
            "content",
            "controls",
            "title",
            "subtitle",
            "label",
            "actions",
        ):
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


# --- Theme and components ---


class TestTheme:
    def test_the_theme_is_buildable(self) -> None:
        theme = build_theme()

        assert theme.use_material3 is True
        assert theme.color_scheme_seed

    def test_the_app_bar_title_is_painted(self) -> None:
        """Flutter drops its default title colour once a style is supplied.

        Without a colour named here the title rendered white on a white app
        bar on the phone.
        """
        appbar_theme = build_theme().appbar_theme

        assert appbar_theme is not None
        assert appbar_theme.title_text_style is not None
        assert appbar_theme.title_text_style.color
        assert appbar_theme.color

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
        assert built.on_click is None
        assert built.ink is False

    def test_a_pill_that_folds_something_open_is_tappable(self) -> None:
        taps: list[int] = []
        # As Flet delivers it: a handler taking the event, called with one.
        built: Any = pill(
            "Unit 1",
            icon=ft.Icons.MENU_BOOK_ROUNDED,
            trailing=ft.Icons.EXPAND_MORE_ROUNDED,
            on_click=lambda _: taps.append(1),
            tooltip="What this unit covers",
        )

        built.on_click(None)

        assert taps == [1]
        assert built.ink is True
        assert built.tooltip == "What this unit covers"

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

    def test_the_lesson_buttons_are_thumb_sized(self) -> None:
        check = primary_action("Check", icon=ft.Icons.TASK_ALT_ROUNDED)
        reveal = secondary_action("Reveal")

        assert check.height == reveal.height
        assert check.expand is True
        assert reveal.expand is False

    def test_an_action_bar_carries_its_buttons(self) -> None:
        bar = action_bar(secondary_action("Reveal"), primary_action("Check"))

        assert "Reveal" in rendered(bar)
        assert bar.border is not None

    def test_a_sheet_is_rounded_at_the_top_only(self) -> None:
        raised = sheet(ft.Text("Correct!"), bgcolor=ft.Colors.PRIMARY_CONTAINER)

        assert "Correct!" in rendered(raised)
        assert isinstance(raised.border_radius, ft.BorderRadius)
        assert raised.border_radius.bottom_left == 0

    def test_a_progress_track_reports_its_share(self) -> None:
        assert progress_track(0.4).value == 0.4

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


# --- Practice screen ---


@pytest.fixture
def wrong_services(
    config_store: ConfigStore,
    content: ContentLibrary,
    stats: StatsStore,
    config: AppConfig,
) -> Services:
    """Services whose grader marks every answer wrong."""
    return Services(
        config_store=config_store,
        content=content,
        stats=stats,
        config=config,
        transport=reply_transport('{"is_correct": false, "answer_idx": []}'),
    )


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


def _button(control: Any, label: str) -> Any:
    """Return the button whose label starts with ``label``.

    Args:
        control: Where to look.
        label: The start of the label, which is enough to tell the buttons of
            one screen apart.

    Returns:
        The button.

    Raises:
        AssertionError: If no button carries that label.
    """
    for kind in (ft.FilledButton, ft.OutlinedButton, ft.TextButton, ft.IconButton):
        for button in _all(control, kind):
            if label in rendered(button):
                return button
    raise AssertionError(f"no button labelled {label!r}")


def _pill(control: Any, label: str) -> Any:
    """Return the tappable pill carrying ``label``.

    Args:
        control: Where to look.
        label: The pill's text.

    Returns:
        The pill.

    Raises:
        AssertionError: If no tappable pill carries that text.
    """
    for container in _all(control, ft.Container):
        if container.on_click is not None and label in texts(container.content):
            return container
    raise AssertionError(f"no tappable pill labelled {label!r}")


async def _start(screen: PracticeScreen, length: int | None = None) -> Lesson:
    """Start a lesson on the seeded topic, optionally shortened.

    Args:
        screen: The screen to drive.
        length: How many questions the run should hold. A short run is what
            makes finishing one testable.

    Returns:
        The lesson now on screen.
    """
    await screen.start_lesson(1, "Present Tenses")
    lesson = screen._session.lesson
    assert lesson is not None
    if length is not None:
        lesson.length = length
    return lesson


async def _answer(screen: PracticeScreen, typed: str = "is doing") -> None:
    """Type an answer and check it.

    Args:
        screen: The screen to drive.
        typed: What the user wrote.
    """
    screen._answer.value = typed
    await screen._on_check()


class TestSwitchRow:
    """A sentence-length label must wrap, not run off the panel's edge."""

    def test_the_label_is_a_sibling_free_to_wrap(self) -> None:
        async def handler(_: object) -> None:
            """Stand in for the screen's handler."""

        row = switch_row(
            "Show the grammar rule after each answer", value=True, on_change=handler
        )

        label, switch = row.controls
        assert isinstance(switch, ft.Switch)
        assert switch.label is None
        assert isinstance(label, ft.Text)
        assert label.expand
        assert "grammar rule" in rendered(row)

    def test_the_switch_carries_the_value_and_handler(self) -> None:
        async def handler(_: object) -> None:
            """Stand in for the screen's handler."""

        row = switch_row("On or off", value=False, on_change=handler)
        switch = row.controls[-1]

        assert isinstance(switch, ft.Switch)
        assert switch.value is False
        assert switch.on_change is handler


class TestHomeView:
    """The course list: what it draws, and what a tap on it reports."""

    def _view(self, started: list[tuple[int | None, str]]) -> HomeView:
        return HomeView(
            on_start=lambda topic_id, name: started.append((topic_id, name))
        )

    def test_a_first_visit_offers_a_lesson_and_no_topics(self) -> None:
        column = ft.Column(controls=self._view([]).build(HomeState()))

        body = rendered(column)
        assert "First day" in body
        assert "0/10 today" in body
        assert "Start a lesson" in body
        assert "No topics to show" in body

    def test_a_streak_and_a_met_goal_are_reported(self) -> None:
        state = HomeState(
            summary=StatsSummary(
                day_streak=3,
                recent_days=(DayStat(day=date(2026, 3, 14), attempts=12, correct=9),),
            )
        )

        body = rendered(ft.Column(controls=self._view([]).build(state)))

        assert "3 day streak" in body
        assert "10/10 today" in body
        assert "Daily goal reached" in body

    def test_a_practised_topic_carries_its_tally(self) -> None:
        state = HomeState(
            topics=(Topic(id=1, name="Present Tenses", unit_count=12),),
            topic_stats={"Present Tenses": TopicStat("Present Tenses", 8, 6)},
        )

        column = ft.Column(controls=self._view([]).build(state))

        assert "12 units - 6/8" in rendered(column)
        assert any(bar.value == 0.75 for bar in _all(column, ft.ProgressBar))

    def test_the_lesson_button_asks_for_a_mixed_run(self) -> None:
        started: list[tuple[int | None, str]] = []
        column = ft.Column(controls=self._view(started).build(HomeState()))

        _button(column, "Start a lesson").on_click(None)

        assert started == [(None, MIXED_LESSON_LABEL)]

    def test_a_topic_card_asks_for_that_topic(self) -> None:
        started: list[tuple[int | None, str]] = []
        state = HomeState(topics=(Topic(id=7, name="Past Tenses", unit_count=1),))
        column = ft.Column(controls=self._view(started).build(state))

        cards = [item for item in _all(column, ft.Container) if item.on_click]
        cards[0].on_click(None)

        assert started == [(7, "Past Tenses")]

    def test_the_last_topic_is_offered_again(self) -> None:
        started: list[tuple[int | None, str]] = []
        state = HomeState(last_topic_id=1, last_topic_name="Present Tenses")
        column = ft.Column(controls=self._view(started).build(state))

        _button(column, "Again: Present Tenses").on_click(None)

        assert started == [(1, "Present Tenses")]

    def test_the_setup_notice_reaches_the_settings_tab(self) -> None:
        opened: list[bool] = []
        view = HomeView(
            on_start=lambda _topic_id, _name: None,
            on_open_settings=lambda: opened.append(True),
        )
        column = ft.Column(controls=view.build(HomeState(problem="API key is not set")))

        assert "API key is not set" in rendered(column)
        _button(column, "Open settings").on_click(None)

        assert opened == [True]

    def test_without_a_settings_hook_the_notice_has_no_button(self) -> None:
        state = HomeState(problem="API key is not set")

        column = ft.Column(controls=self._view([]).build(state))

        assert "Open settings" not in rendered(column)


class TestPracticeHome:
    async def test_it_opens_on_the_lesson_card_and_the_topics(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.reload()

        body = rendered(screen)
        assert "Start a lesson" in body
        assert "PRACTISE A TOPIC" in body
        assert "Present Tenses" in body
        assert "1 unit" in body

    async def test_the_day_card_reports_today(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.reload()
        await _start(screen)
        await _answer(screen)

        await screen._on_done()

        assert "1/10 today" in rendered(screen)

    async def test_a_practised_topic_shows_its_tally(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.reload()
        await _start(screen)
        await _answer(screen)

        await screen._on_done()

        assert "1 unit - 1/1" in rendered(screen)

    async def test_an_unconfigured_app_says_what_is_missing(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(AppConfig())
        screen = PracticeScreen(page, services, on_open_settings=lambda: None)

        body = rendered(screen)
        assert "API key is not set" in body
        assert "Open settings" in body

    async def test_the_setup_banner_can_reach_the_settings_tab(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(AppConfig())
        opened: list[bool] = []
        screen = PracticeScreen(
            page, services, on_open_settings=lambda: opened.append(True)
        )

        _button(screen.controls[0], "Open settings").on_click(None)

        assert opened == [True]

    async def test_without_a_settings_hook_the_banner_has_no_button(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(AppConfig())
        screen = PracticeScreen(page, services)

        assert "Open settings" not in rendered(screen)

    async def test_a_topic_card_starts_a_lesson_on_it(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await screen.reload()
        topics = await services.content.list_topics()

        cards = [item for item in _all(screen, ft.Container) if item.on_click]
        cards[0].on_click(None)
        await page.drain()

        lesson = screen._session.lesson
        assert lesson is not None
        assert lesson.topic_id == topics[0].id
        assert lesson.topic_name == topics[0].name

    async def test_the_last_topic_is_offered_again(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        await screen._on_leave()

        assert "Again: Present Tenses" in rendered(screen)

        _button(screen, "Again: Present Tenses").on_click(None)
        await page.drain()

        lesson = screen._session.lesson
        assert lesson is not None
        assert lesson.topic_id == 1

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

        await screen.reload()
        await screen.start_lesson(1, "Present Tenses")

        assert "database is missing" in page.snack_texts()[0]
        assert "database is missing" in page.snack_texts()[1]
        assert screen._session.lesson is None
        assert "No topics to show" in rendered(screen)

    def test_refreshing_redraws(self, page: FakePage, services: Services) -> None:
        screen = PracticeScreen(page, services)
        services.stage(AppConfig())

        screen.repaint()

        assert "API key is not set" in rendered(screen)


class TestLessonFlow:
    async def test_starting_puts_a_question_on_screen(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await _start(screen)

        body = rendered(screen)
        assert "Present Tenses" in body
        assert "Unit 1" in body
        assert "1/10" in body
        assert "Check" in body

    async def test_the_heading_is_the_sentence_to_answer(
        self, page: FakePage, services: Services
    ) -> None:
        """Two numbers labelled alike, meaning different things, read as a bug.

        The bar says how far into the run the user is, and says it once. The
        heading is the book's own numbering -- the sentence of the printed
        exercise this question is -- which is the number the picture is read
        with.
        """
        screen = PracticeScreen(page, services)

        await _start(screen)

        body = rendered(screen)
        assert "Sentence 2" in body
        assert "Question" not in body
        assert "1/10" in body

    async def test_a_mixed_lesson_labels_the_topic_it_landed_on(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        _button(screen, "Start a lesson").on_click(None)
        await page.drain()

        lesson = screen._session.lesson
        assert lesson is not None
        assert lesson.topic_id is None
        assert lesson.topic_name == MIXED_LESSON_LABEL
        assert lesson.active is not None
        assert lesson.active.topic_name in {"Present Tenses", "Past Tenses"}

    async def test_the_exercise_image_is_shown(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await _start(screen)

        assert _find(screen, ft.Image).src == b"\x89PNG\r\n\x1a\n"

    async def test_the_crop_is_never_rounded_off(
        self, page: FakePage, services: Services
    ) -> None:
        """A radius on the picture clips the corners of a page of the book."""
        screen = PracticeScreen(page, services)

        await _start(screen)

        assert _find(screen, ft.Image).border_radius is None

    async def test_an_exercise_without_a_picture_says_so(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.start_lesson(2, "Past Tenses")

        assert "no picture" in rendered(screen)

    async def test_an_empty_topic_leaves_the_user_at_home(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await screen.start_lesson(999, "Nothing")

        assert "No exercises found" in page.snack_texts()[0]
        assert screen._session.lesson is None
        assert "Start a lesson" in rendered(screen)

    async def test_answering_raises_the_verdict_sheet(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)

        await _answer(screen)

        body = rendered(screen)
        assert "is doing" in body
        assert "Continue" in body
        # The question is still on screen: nothing scrolled away under a reply.
        assert "Sentence 2" in body
        # The bar used to announce the next question over this one's verdict.
        assert "1/10" in body
        assert "1/10" in body

    async def test_a_correct_answer_is_green(
        self, page: FakePage, services: Services
    ) -> None:
        """Right is green. The brand blue read as another announcement."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        await _answer(screen)

        sheet_shown: Any = screen.controls[-1]
        assert sheet_shown.bgcolor == CORRECT
        assert _button(sheet_shown, "Continue").bgcolor == ON_CORRECT
        assert _find(sheet_shown, ft.Icon).color == ON_CORRECT

    async def test_a_wrong_answer_is_not_green(
        self, page: FakePage, wrong_services: Services
    ) -> None:
        screen = PracticeScreen(page, wrong_services)
        await _start(screen)

        await _answer(screen)

        sheet_shown: Any = screen.controls[-1]
        assert sheet_shown.bgcolor == ft.Colors.ERROR_CONTAINER

    async def test_a_correct_answer_keeps_the_sheet_short(
        self, page: FakePage, services: Services
    ) -> None:
        """Confirmation should be quick to dismiss, so the sentence is left out."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        await _answer(screen)

        assert "He **is doing** it." not in rendered(screen)

    async def test_a_wrong_answer_shows_the_whole_sentence(
        self, page: FakePage, wrong_services: Services
    ) -> None:
        screen = PracticeScreen(page, wrong_services)
        await _start(screen)

        await _answer(screen, "did")

        assert "He **is doing** it." in rendered(screen)

    async def test_the_answer_field_keeps_what_was_typed(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)

        await _answer(screen, "is doing")

        assert screen._answer.value == "is doing"
        assert screen._answer.read_only is True

    async def test_a_graded_answer_is_recorded(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        lesson = await _start(screen)

        await _answer(screen)

        summary = await services.stats.summary()
        assert summary.total == 1
        assert summary.correct == 1
        assert lesson.outcomes == [True]

    async def test_the_rule_is_folded_away_until_it_is_asked_for(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        await _answer(screen)

        assert "Rule 1A" in rendered(screen)
        assert "Use present continuous" not in rendered(screen)

        screen._on_toggle_rule()

        assert "Use present continuous" in rendered(screen)

    async def test_the_rule_toggle_is_hidden_when_rules_are_off(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(replace(services.config, show_rules=False))
        screen = PracticeScreen(page, services)
        await _start(screen)

        await _answer(screen)

        assert "Rule 1A" not in rendered(screen)

    async def test_an_empty_answer_is_refused(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)

        await _answer(screen, "   ")

        assert "Type your answer first" in page.snack_texts()[0]

    async def test_a_busy_screen_shows_progress(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen._busy = True
        screen.render()

        assert "Checking your answer" in rendered(screen)

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
        lesson = await _start(screen)

        await _answer(screen)

        body = rendered(screen)
        # In the sheet, not a snack bar: a snack covers the button that moves on.
        assert "Could not grade that" in body
        assert page.snack_texts() == []
        assert "is doing" in body
        assert lesson.outcomes == [False]
        assert (await stats.summary()).total == 0

    async def test_the_reason_a_grading_failed_ends_in_one_full_stop(
        self,
        page: FakePage,
        config_store: ConfigStore,
        content: ContentLibrary,
        stats: StatsStore,
        config: AppConfig,
    ) -> None:
        """Some provider messages end in a full stop and some do not."""
        broken = Services(
            config_store=config_store,
            content=content,
            stats=stats,
            config=config,
            transport=httpx.MockTransport(lambda _: httpx.Response(500, json={})),
        )
        broken.client._sleep = _instant
        screen = PracticeScreen(page, broken)
        await _start(screen)

        await _answer(screen)

        assert ".." not in rendered(screen)
        assert screen._grading_error is not None
        assert screen._grading_error.endswith(".")

    async def test_a_fresh_question_drops_the_previous_failure(
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
            transport=httpx.MockTransport(lambda _: httpx.Response(500, json={})),
        )
        broken.client._sleep = _instant
        screen = PracticeScreen(page, broken)
        await _start(screen)
        await _answer(screen)
        assert screen._grading_error is not None

        await screen._on_continue()

        assert screen._grading_error is None
        assert "Could not grade that" not in rendered(screen)

    async def test_revealing_spends_the_question_but_earns_nothing(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        lesson = await _start(screen)

        await screen._on_reveal()

        assert "is doing" in rendered(screen)
        assert lesson.outcomes == [False]
        assert (await services.stats.summary()).total == 0

    async def test_an_open_question_says_the_book_prints_no_answer(
        self, page: FakePage, services: Services
    ) -> None:
        """Showing a canonical answer to a free-form question would mislead."""
        screen = PracticeScreen(page, services)
        await screen.start_lesson(2, "Past Tenses")

        await screen._on_reveal()

        assert "open-ended" in rendered(screen)

    async def test_a_closed_question_with_no_answer_is_not_called_open_ended(
        self, page: FakePage, services: Services
    ) -> None:
        """An empty reveal used to read as open-ended whatever caused it.

        `validate` reports a closed question with no rows in question_answers
        as a failure, so it happens -- and telling the student the question
        was free-form says their own sentence was the point.
        """
        screen = PracticeScreen(page, services)
        lesson = await _start(screen)
        assert lesson.active is not None
        lesson.active.answers = ()

        await screen._on_reveal()

        note = rendered(screen)
        assert "The book records no answer" in note
        assert "open-ended" not in note

    async def test_continuing_draws_the_next_question(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        lesson = await _start(screen)
        await _answer(screen)

        await screen._on_continue()

        assert lesson.active is not None
        assert lesson.active.is_revealed is False
        assert screen._answer.value == ""
        assert "2/10" in rendered(screen)

    async def test_a_lesson_that_cannot_draw_on_stays_put(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        lesson = await _start(screen)
        await _answer(screen)
        lesson.topic_id = 999

        await screen._on_continue()

        assert "No exercises found" in page.snack_texts()[0]
        assert lesson.active is not None
        assert lesson.active.is_revealed is True

    async def test_the_unit_chip_says_what_the_unit_covers(
        self, page: FakePage, services: Services
    ) -> None:
        """It used to be a dialog behind the chip. Unfolding it is enough."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        assert "Present Continuous" not in rendered(screen)

        _pill(screen, "Unit 1").on_click(None)

        assert "Present Continuous" in rendered(screen)
        assert page.dialogs == []

    async def test_tapping_the_unit_chip_again_folds_it_away(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        _pill(screen, "Unit 1").on_click(None)

        _pill(screen, "Unit 1").on_click(None)

        assert "Present Continuous" not in rendered(screen)

    async def test_a_new_question_folds_the_unit_away(
        self, page: FakePage, services: Services
    ) -> None:
        """The line belongs to the question being read, not to the lesson."""
        screen = PracticeScreen(page, services)
        await _start(screen)
        _pill(screen, "Unit 1").on_click(None)
        await _answer(screen)

        await screen._on_continue()

        assert "Present Continuous" not in rendered(screen)


class TestZoomingThePicture:
    """The magnified crop is a state of the screen, never a box over it."""

    async def test_opening_the_zoom_gives_it_the_whole_screen(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)

        screen._open_zoom()

        assert _find(screen, ft.InteractiveViewer) is not None
        assert page.dialogs == []
        # The question is not underneath it: this replaced the lesson.
        assert "YOUR ANSWER" not in rendered(screen)

    async def test_the_magnified_picture_is_given_the_frame_to_draw_in(
        self, page: FakePage, services: Services
    ) -> None:
        """A viewer with no frame of its own drew an empty screen.

        Centring it inside its container handed it loose constraints, under
        which it measured itself at nothing: the bar arrived over a blank
        page, with the crop nowhere on it.
        """
        screen = PracticeScreen(page, services)
        await _start(screen)

        screen._open_zoom()

        viewer = _find(screen, ft.InteractiveViewer)
        assert viewer.expand is True
        assert _find(viewer, ft.Image).src == b"\x89PNG\r\n\x1a\n"

    async def test_back_closes_the_zoom_before_the_lesson(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen._open_zoom()

        assert screen.handle_back() is True

        assert _find_or_none(screen, ft.InteractiveViewer) is None
        assert screen._session.lesson is not None
        assert "YOUR ANSWER" in rendered(screen)

    async def test_an_exercise_with_no_picture_cannot_be_zoomed(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        lesson = await screen.start_lesson(2, "Past Tenses") or screen._session.lesson

        assert lesson is not None
        screen._open_zoom()

        assert _find_or_none(screen, ft.InteractiveViewer) is None
        assert "YOUR ANSWER" in rendered(screen)


class TestLeavingALesson:
    async def test_the_cross_asks_first(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)

        screen.request_leave()

        assert "Leave this lesson?" in rendered(screen)
        assert page.dialogs == []
        assert screen._session.lesson is not None

    async def test_staying_puts_the_question_back(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen.request_leave()

        screen._stay()

        assert "Leave this lesson?" not in rendered(screen)
        assert screen._session.lesson is not None
        assert "Check" in rendered(screen)

    async def test_confirming_goes_back_home(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen.request_leave()

        await screen._on_leave()

        assert screen._session.lesson is None
        assert "Start a lesson" in rendered(screen)

    async def test_back_asks_rather_than_dropping_the_run(
        self, page: FakePage, services: Services
    ) -> None:
        """Android's Back mid-lesson used to close the app outright."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        assert screen.handle_back() is True

        assert "Leave this lesson?" in rendered(screen)
        assert screen._session.lesson is not None

    async def test_back_again_stays_in_the_lesson(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen.request_leave()

        assert screen.handle_back() is True

        assert "Leave this lesson?" not in rendered(screen)
        assert screen._session.lesson is not None

    async def test_back_on_the_home_screen_is_not_this_screen_s(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        assert screen.handle_back() is False

    async def test_back_on_the_result_closes_the_lesson(
        self, page: FakePage, services: Services
    ) -> None:
        """Nothing is left to confirm once the run is over."""
        screen = PracticeScreen(page, services)
        await _start(screen, length=1)
        await _answer(screen)
        await screen._on_continue()

        assert screen.handle_back() is True
        await page.drain()

        assert screen._session.lesson is None
        assert "Start a lesson" in rendered(screen)

    async def test_the_next_lesson_does_not_open_on_the_question_just_asked(
        self, page: FakePage, services: Services
    ) -> None:
        """The flag outlived its lesson, so the next one began part-way out."""
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen.request_leave()
        await screen._on_leave()

        await _start(screen)

        assert "Leave this lesson?" not in rendered(screen)
        assert "Check" in rendered(screen)

    async def test_the_shell_is_told_when_a_lesson_owns_the_screen(
        self, page: FakePage, services: Services
    ) -> None:
        seen: list[bool] = []
        screen = PracticeScreen(page, services, on_lesson_change=seen.append)

        await _start(screen)
        await screen._on_leave()

        assert seen == [True, False]


class TestLessonResult:
    async def test_the_last_question_offers_the_result(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen, length=1)

        await _answer(screen)

        assert "See your result" in rendered(screen)

    async def test_finishing_shows_the_score(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen, length=1)
        await _answer(screen)

        await screen._on_continue()

        body = rendered(screen)
        assert "Lesson complete" in body
        assert "1 of 1 correct" in body
        assert "100%" in body

    async def test_practising_again_starts_another_run(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen, length=1)
        await _answer(screen)
        await screen._on_continue()

        _button(screen.controls[1], "Practise again").on_click(None)
        await page.drain()

        lesson = screen._session.lesson
        assert lesson is not None
        assert lesson.answered == 0
        assert lesson.active is not None

    async def test_done_returns_to_the_home_screen(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen, length=1)
        await _answer(screen)
        await screen._on_continue()

        await screen._on_done()

        assert screen._session.lesson is None
        assert "Start a lesson" in rendered(screen)


async def _instant(_: float) -> None:
    """Skip the retry delay."""


# --- Stats screen ---


class TestStatsScreen:
    async def test_an_empty_history_says_where_to_start(
        self, page: FakePage, services: Services
    ) -> None:
        screen = StatsScreen(page, services)

        await screen.reload()

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

        await screen.reload()

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
        await screen.reload()

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
        await screen.reload()

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

        await screen.reload()

        assert "more topics" in rendered(screen)


# --- Model picker ---


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

        assert "20 more matches" in rendered(picker)
        assert len(picker._list.controls) == MAX_RESULTS + 1

    def test_one_hidden_match_is_counted_in_the_singular(self) -> None:
        many = [
            ModelInfo(id=f"vendor/model-{index:03d}", name=f"Model {index}")
            for index in range(MAX_RESULTS + 1)
        ]
        picker = ModelPicker(
            provider_label="OpenRouter",
            models=many,
            selected="",
            on_select=lambda _: None,
            on_refresh=lambda: None,
        )

        assert "1 more match - " in rendered(picker)

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

        assert picker._count.value == "1/3"

    def test_the_count_is_shown_inside_the_search_field(
        self, catalogue: list[ModelInfo]
    ) -> None:
        """On its own line it cost the list a whole model."""
        picker, _, _ = self._picker(catalogue)

        assert picker._search.suffix is picker._count

    def test_the_picker_closes_from_its_title(self, catalogue: list[ModelInfo]) -> None:
        """The button along the bottom cost the list another model."""
        picker, _, _ = self._picker(catalogue)

        assert picker.actions == []
        closers = [
            button
            for button in _all(picker.title, ft.IconButton)
            if button.tooltip == "Close"
        ]
        assert len(closers) == 1
        closers[0].on_click()


# --- Settings screen ---


class TestSettingsScreen:
    async def test_it_shows_every_section(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen.reload()

        body = rendered(screen)
        for section in (
            "PROVIDER",
            "MODEL",
            "REASONING",
            "PRACTICE",
            "PROXY",
            "ADVANCED",
            "ABOUT",
        ):
            assert section in body

    async def test_the_folds_say_what_they_hold_while_shut(
        self, page: FakePage, services: Services
    ) -> None:
        """A heading worth reading is what makes folding them away honest."""
        screen = SettingsScreen(page, services)

        await screen.reload()

        body = rendered(screen)
        assert "Off - calls go straight to the provider" in body
        assert "0.7 temp" in body
        assert "2048 tokens" in body

    async def test_a_saved_setting_leaves_an_open_fold_open(
        self, page: FakePage, services: Services
    ) -> None:
        """The slider lives inside the fold, so closing it mid-drag is a bug."""
        screen = SettingsScreen(page, services)
        screen._on_advanced_fold(
            _event(ft.ExpansionTile(title=ft.Text("Advanced")), data="true")
        )

        await screen._on_temperature(_event(ft.Slider(value=0.4)))

        folds = [
            tile
            for tile in _all(screen, ft.ExpansionTile)
            if "ADVANCED" in rendered(tile.title)
        ]
        assert [fold.expanded for fold in folds] == [True]

    async def test_turning_the_proxy_on_shows_its_fields(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen._on_proxy_enabled(_event(ft.Switch(value=True)))

        folds = [
            tile
            for tile in _all(screen, ft.ExpansionTile)
            if "PROXY" in rendered(tile.title)
        ]
        assert [fold.expanded for fold in folds] == [True]

    async def test_closing_a_fold_is_remembered(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(replace(services.config, proxy=ProxyConfig(enabled=True)))
        screen = SettingsScreen(page, services)

        screen._on_proxy_fold(
            _event(ft.ExpansionTile(title=ft.Text("Proxy")), data=False)
        )
        await screen.reload()

        folds = [
            tile
            for tile in _all(screen, ft.ExpansionTile)
            if "PROXY" in rendered(tile.title)
        ]
        assert [fold.expanded for fold in folds] == [False]

    async def test_every_provider_segment_label_is_sized_to_fit(
        self, page: FakePage, services: Services
    ) -> None:
        """At 360dp the default size wrapped "OpenRouter" mid-word."""
        screen = SettingsScreen(page, services)
        await screen.reload()

        values = {known.value for known in Provider}
        chooser = next(
            button
            for button in _all(screen, ft.SegmentedButton)
            if {segment.value for segment in button.segments} == values
        )

        labels = [segment.label for segment in chooser.segments]
        assert len(labels) == len(Provider)
        for label in labels:
            assert isinstance(label, ft.Text)
            assert label.size == SEGMENT_LABEL_SIZE

    async def test_the_about_section_counts_the_book(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        await screen.reload()

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
        services.stage(services.config.with_active(model_supports_thinking=True))
        screen = SettingsScreen(page, services)

        await screen._on_thinking("high")

        assert services.config.active.thinking is ThinkingLevel.HIGH

    async def test_choosing_a_level_schedules_the_save(
        self, page: FakePage, services: Services
    ) -> None:
        """The list's callback cannot await, so the work is handed to the page."""
        services.stage(services.config.with_active(model_supports_thinking=True))
        screen = SettingsScreen(page, services)

        screen._choose_thinking(_event(ft.Dropdown(value="medium")))
        await page.drain()

        assert services.config.active.thinking is ThinkingLevel.MEDIUM

    def test_every_level_is_offered_on_the_list(
        self, page: FakePage, services: Services
    ) -> None:
        """Six ordered levels are a list, not a block of wrapped chips."""
        services.stage(services.config.with_active(model_supports_thinking=True))
        screen = SettingsScreen(page, services)

        levels = _find(screen.controls[2], ft.Dropdown)

        assert [option.text for option in levels.options] == [
            level.label for level in supported_thinking_levels(Provider.OPENROUTER)
        ]
        assert levels.value == ThinkingLevel.OFF.value
        # Material sizes a dropdown to its longest entry, not to its panel.
        assert levels.expand is True

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

    async def test_the_catalogue_enables_thinking_for_a_stored_model(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        """The stored flag is a cache, not the authority.

        A model restored from the settings file carries whatever the app knew
        when it was picked -- nothing, for a file written before capabilities
        were recorded. Once a catalogue is in hand it says what the model can
        do, and the control has to follow it rather than the stale flag.
        """
        services.stage(services.config.with_active(model_supports_thinking=False))
        services._catalogues[Provider.OPENROUTER] = catalogue
        screen = SettingsScreen(page, services)

        assert not any(chip.disabled for chip in _all(screen.controls[2], ft.Chip))
        assert "no thinking control" not in rendered(screen)

    async def test_a_fetched_catalogue_corrects_the_stored_capabilities(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        """The request is built from the stored flags, so they must agree."""
        services.stage(
            services.config.with_active(
                model_supports_thinking=False, model_supports_json=False
            )
        )
        services._catalogues[Provider.OPENROUTER] = catalogue
        screen = SettingsScreen(page, services)

        await screen._reconcile_capabilities()

        active = services.config_store.load().active
        assert active.model_supports_thinking is True
        assert active.model_supports_json is True

    async def test_reconciling_an_unlisted_model_changes_nothing(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(services.config.with_active(model="vendor/not-in-catalogue"))
        screen = SettingsScreen(page, services)

        await screen._reconcile_capabilities()

        assert services.config.active.model_supports_thinking is False

    async def test_choosing_a_model_that_cannot_think_resets_the_level(
        self, page: FakePage, services: Services, catalogue: list[ModelInfo]
    ) -> None:
        services.stage(
            services.config.with_active(
                model_supports_thinking=True, thinking=ThinkingLevel.HIGH
            )
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
        services.stage(replace(services.config, proxy=ProxyConfig(enabled=True)))
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
        services.stage(replace(services.config, proxy=ProxyConfig(enabled=True)))
        screen = SettingsScreen(page, services)

        screen._stage_proxy_port(_event(ft.TextField(value="0")))

        assert services.config.proxy.port is None

    async def test_a_port_above_the_maximum_is_dropped(
        self, page: FakePage, services: Services
    ) -> None:
        """Staged and read back used to disagree about the range.

        Anything made of digits was written to settings.json, and the launch
        after that quietly dropped it -- so a proxy the user had configured
        and tested was simply off, with the screen blaming a missing host.
        """
        services.stage(replace(services.config, proxy=ProxyConfig(enabled=True)))
        screen = SettingsScreen(page, services)

        screen._stage_proxy_port(_event(ft.TextField(value="99999")))

        assert services.config.proxy.port is None

    async def test_the_proxy_scheme_is_saved(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(replace(services.config, proxy=ProxyConfig(enabled=True)))
        screen = SettingsScreen(page, services)

        await screen._on_proxy_scheme(
            _event(ft.SegmentedButton(segments=[], selected=["socks5"]))
        )

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

    async def test_a_refresh_while_one_is_in_flight_is_ignored(
        self, page: FakePage, services: Services
    ) -> None:
        """Its twin has this guard; only a popped dialog stood in for it here."""
        screen = SettingsScreen(page, services)
        screen._loading_models = True

        await screen._reload_models()

        assert page.popped == 0

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


def _event(control: Any, data: Any = None) -> Any:
    """Return something shaped like a Flet event for one control.

    Args:
        control: The control the event came from.
        data: The event's payload, for the handlers that read one.

    Returns:
        An object exposing ``control`` and ``data``.
    """
    return type("Event", (), {"control": control, "data": data})()


# --- The shell ---


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

    async def test_the_chrome_is_labelled_by_the_screens_themselves(
        self, page: FakePage, services: Services
    ) -> None:
        """A fourth tab is one entry in the list, not six edits in the shell."""
        app = PracticeApp(page, services)

        await app.start()

        assert page.appbar.title.value == app.screens[0].tab_title
        assert [d.label for d in page.navigation_bar.destinations] == [
            screen.tab_label for screen in app.screens
        ]

    async def test_every_screen_is_loaded_at_startup(
        self, page: FakePage, services: Services, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One of the three used to be called without being awaited."""
        app = PracticeApp(page, services)
        reloaded: list[str] = []
        for screen in app.screens:
            name = type(screen).__name__

            async def record(name: str = name) -> None:
                reloaded.append(name)

            monkeypatch.setattr(screen, "reload", record)

        await app.start()

        assert reloaded == [type(s).__name__ for s in app.screens]

    async def test_the_page_going_away_releases_the_pool(
        self, page: FakePage, services: Services
    ) -> None:
        """The one shutdown a phone app gets."""
        app = PracticeApp(page, services)
        await app.start()
        client = services.client
        _ = client._http()

        await page.on_disconnect()

        assert client._client is None


class TestScreen:
    """What the shell needs from a pane, and what it gets for free."""

    def test_a_screen_must_say_how_it_draws_itself(self) -> None:
        with pytest.raises(NotImplementedError):
            Screen().render()

    async def test_reloading_a_screen_with_nothing_to_read_redraws_it(self) -> None:
        drawn: list[int] = []

        class Bare(Screen):
            def render(self) -> None:
                drawn.append(1)

        await Bare().reload()

        assert drawn == [1]

    def test_a_screen_spends_no_back_gesture_by_default(self) -> None:
        assert Screen().handle_back() is False


class TestTheBackGesture:
    """Back is a step inside the app, not a way out of it."""

    async def test_the_root_view_hands_the_gesture_over(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)

        await app.start()

        assert page.root_view.can_pop is False
        assert page.root_view.on_confirm_pop == app._on_confirm_pop

    async def test_nothing_open_on_the_practice_tab_closes_the_app(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        handler = page.root_view.on_confirm_pop
        assert handler is not None
        await handler(
            ft.Event(name="confirm_pop", control=cast("ft.View", page.root_view))
        )

        assert page.root_view.confirmed == [True]

    async def test_another_tab_goes_back_to_practice_instead(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()
        await app.select_tab(SETTINGS_TAB)

        assert await app.handle_back() is False

        assert app._index == PRACTICE_TAB

    async def test_a_running_lesson_is_asked_about_first(
        self, page: FakePage, services: Services
    ) -> None:
        """Ten questions in, Back used to end the app and drop the run."""
        app = PracticeApp(page, services)
        await app.start()
        await app.practice.start_lesson(1, "Present Tenses")

        assert await app.handle_back() is False

        assert "Leave this lesson?" in rendered(app.practice)
        assert app.practice._session.lesson is not None

    async def test_each_tab_shows_its_screen(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        for index in (STATS_TAB, SETTINGS_TAB, PRACTICE_TAB):
            await app.select_tab(index)

            assert app._body.content is app._panes[index]
            assert page.navigation_bar.selected_index == index

    async def test_the_tab_title_follows_the_tab(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        await app.select_tab(STATS_TAB)

        assert page.appbar.title.value == "Progress"

    async def test_every_tab_switch_pushes_the_page(
        self, page: FakePage, services: Services
    ) -> None:
        """The swap has to be sent, not just made.

        The screen a switch loads pushes itself, and that first explicit push
        cancels the automatic one Flet would have sent when the handler
        returned. So a tab visited a second time -- when the pane already has
        a parent and its push therefore fires -- used to leave the phone on
        the previous tab, showing the previous title, with only the navigation
        bar's own highlight moving.
        """
        app = PracticeApp(page, services)
        await app.start()

        for visit in (STATS_TAB, SETTINGS_TAB, STATS_TAB, PRACTICE_TAB, STATS_TAB):
            before = page.updates
            await app.select_tab(visit)

            assert page.updates > before, f"tab {visit} was swapped but not pushed"

    async def test_a_lesson_pushes_the_chrome_it_hid(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()
        before = page.updates

        await app.practice.start_lesson(1, "Present Tenses")

        assert page.updates > before

    async def test_a_theme_change_pushes_the_page(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()
        before = page.updates

        app._settings_changed()

        assert page.updates > before

    async def test_switching_tabs_keeps_the_open_lesson(
        self, page: FakePage, services: Services
    ) -> None:
        """Losing a half-answered lesson would be the app's worst bug."""
        app = PracticeApp(page, services)
        await app.start()
        await app.practice.start_lesson(1, "Present Tenses")

        await app.select_tab(STATS_TAB)
        await app.select_tab(PRACTICE_TAB)

        # Through what the screen shows rather than the session: the question is up.
        assert "1/10" in rendered(app.practice)

    async def test_a_lesson_takes_the_chrome_off_the_screen(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        await app.practice.start_lesson(1, "Present Tenses")

        assert page.appbar.visible is False
        assert page.navigation_bar.visible is False

        await app.practice._on_leave()

        assert page.appbar.visible is True
        assert page.navigation_bar.visible is True

    async def test_the_navigation_bar_switches_tabs(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        await page.navigation_bar.on_change(
            _event(ft.NavigationBar(selected_index=SETTINGS_TAB, destinations=[]))
        )

        assert app._body.content is app._panes[SETTINGS_TAB]

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
        services.stage(AppConfig())

        app._settings_changed()

        assert "API key is not set" in rendered(app.practice)

    async def test_the_setup_banner_jumps_to_the_settings_tab(
        self, page: FakePage, services: Services
    ) -> None:
        services.stage(AppConfig())
        app = PracticeApp(page, services)
        await app.start()

        app._open_settings()
        await page.drain()

        assert app._body.content is app._panes[SETTINGS_TAB]


# --- Motion ---

_KEYED_ATTRIBUTES = (
    "content",
    "controls",
    "title",
    "subtitle",
    "label",
    "actions",
    "leading",
    "trailing",
)

# Every property Flet can animate implicitly; without a key there is no tween.
_ANIMATED_ATTRIBUTES = (
    "animate",
    "animate_opacity",
    "animate_size",
    "animate_position",
    "animate_offset",
    "animate_scale",
    "animate_rotation",
    "animate_align",
    "animate_margin",
)


def _walk(control: Any, visit: Any) -> None:
    """Call ``visit`` on every control under ``control``, and on each list."""
    if isinstance(control, (list, tuple)):
        visit(control)
        for item in control:
            _walk(item, visit)
        return
    if not isinstance(control, ft.BaseControl):
        return
    visit(control)
    for attribute in _KEYED_ATTRIBUTES:
        _walk(getattr(control, attribute, None), visit)


def _keys_under(control: Any) -> dict[str, Any]:
    """Return every keyed control under ``control``, by key."""
    found: dict[str, Any] = {}

    def visit(node: Any) -> None:
        if isinstance(node, ft.BaseControl) and node.key is not None:
            found[str(node.key)] = node

    _walk(control, visit)
    return found


def _region(control: Any, name: str) -> Any:
    """Return the switcher for region ``name``, wherever it is in the tree."""
    region = _keys_under(control).get(name)
    assert isinstance(region, ft.AnimatedSwitcher), f"no {name!r} region"
    return region


def _state_of(control: Any, region: str) -> str:
    """Return which state region ``name`` is currently showing."""
    return str(_region(control, region).content.key)


def _animated_without_keys(control: Any) -> list[Any]:
    """Return every control that animates a property but has no key to keep it."""
    offenders: list[Any] = []

    def visit(node: Any) -> None:
        if not isinstance(node, ft.BaseControl) or node.key is not None:
            return
        if any(getattr(node, name, None) is not None for name in _ANIMATED_ATTRIBUTES):
            offenders.append(node)

    _walk(control, visit)
    return offenders


def _duplicate_sibling_keys(control: Any) -> list[list[str]]:
    """Return each list of siblings in which one key is used twice."""
    clashes: list[list[str]] = []

    def visit(node: Any) -> None:
        if not isinstance(node, (list, tuple)):
            return
        keys = [
            str(item.key)
            for item in node
            if isinstance(item, ft.BaseControl) and item.key is not None
        ]
        if len(set(keys)) != len(keys):
            clashes.append(keys)

    _walk(control, visit)
    return clashes


class TestMotionVocabulary:
    """Three speeds, one direction each, and no fourth of either."""

    def test_the_durations_are_ordered_by_how_much_moves(self) -> None:
        assert motion.LEAVE_AT_ONCE < motion.LEAVE < motion.FAST
        assert motion.FAST < motion.MEDIUM < motion.SLOW

    def test_what_is_leaving_is_quicker_than_what_arrives(self) -> None:
        """Two halves fading at one rate spend the overlap as a double exposure."""
        for pace in motion.Swap:
            assert pace.value > motion.LEAVE

    def test_every_pace_is_one_of_the_three_durations(self) -> None:
        assert {pace.value for pace in motion.Swap} == {
            motion.FAST,
            motion.MEDIUM,
            motion.SLOW,
        }

    def test_a_key_is_stamped_on_the_control_it_is_given(self) -> None:
        control = ft.Container()

        assert motion.keyed(control, "here") is control
        assert control.key == "here"

    def test_a_state_key_names_the_region_and_then_the_state(self) -> None:
        assert motion.state_key("a.b", "c") == "a.b:c"


class TestSwap:
    """A region outlives the repaint; the state in it is what changes."""

    def test_the_region_is_the_switchers_own_key(self) -> None:
        region = motion.swap(region="r", state="s", content=ft.Container())

        assert isinstance(region, ft.AnimatedSwitcher)
        assert region.key == "r"

    def test_the_state_is_the_contents_key(self) -> None:
        region = motion.swap(region="r", state="s", content=ft.Container())

        assert region.content.key == motion.state_key("r", "s")

    def test_the_pace_sets_how_long_the_arriving_half_takes(self) -> None:
        region = motion.swap(
            region="r", state="s", content=ft.Container(), pace=motion.Swap.SCREEN
        )

        assert region.duration == motion.SLOW
        assert region.reverse_duration == motion.LEAVE

    def test_a_region_that_resizes_drops_the_outgoing_half_at_once(self) -> None:
        """Fading it holds the region at the taller of the two states."""
        region = motion.swap(
            region="r", state="s", content=ft.Container(), resizes=True
        )

        assert region.reverse_duration == motion.LEAVE_AT_ONCE

    def test_a_cross_fade_and_never_a_scale(self) -> None:
        """A pane growing from nothing reads as a pop, not a change of subject."""
        region = motion.swap(region="r", state="s", content=ft.Container())

        assert region.transition == ft.AnimatedSwitcherTransition.FADE


class TestTheShellAnimatesATabChange:
    async def test_the_body_is_one_region_the_tabs_take_turns_in(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)

        await app.start()

        assert isinstance(app._body, ft.AnimatedSwitcher)
        assert app._body.expand is True

    async def test_each_tab_carries_its_own_state_key(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()

        keys = [pane.key for pane in app._panes]

        assert keys == [f"shell.body:{screen.tab_label}" for screen in app.screens]
        assert len(set(keys)) == len(keys)

    async def test_changing_tab_changes_which_state_the_region_holds(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)
        await app.start()
        before = app._body.content

        await app.select_tab(STATS_TAB)

        assert app._body.content is not before
        assert app._body.content.key != before.key

    async def test_a_tab_change_is_the_slowest_thing_in_the_app(
        self, page: FakePage, services: Services
    ) -> None:
        app = PracticeApp(page, services)

        await app.start()

        assert app._body.duration == motion.SLOW


class TestThePracticeScreenAnimatesItsStates:
    """Four screens in three slots, and the slots are the same ones every time."""

    async def test_the_body_names_the_state_it_is_showing(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        assert _state_of(screen, "practice.body") == "practice.body:home"

        await _start(screen)

        assert _state_of(screen, "practice.body") == "practice.body:lesson"

    async def test_the_magnified_picture_is_a_state_of_the_same_slots(
        self, page: FakePage, services: Services
    ) -> None:
        """It replaces the lesson, so it should arrive the way a screen does."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        screen._open_zoom()

        assert _state_of(screen, "practice.body") == "practice.body:zoom"
        assert _state_of(screen, "practice.bar") == "practice.bar:zoom"

    async def test_the_result_is_a_state_of_the_same_slot(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen, length=1)
        await _answer(screen)

        await screen._on_continue()

        assert _state_of(screen, "practice.body") == "practice.body:result"

    async def test_the_slots_keep_their_names_across_every_state(
        self, page: FakePage, services: Services
    ) -> None:
        """A slot renamed between two states is a slot the client remounts."""
        screen = PracticeScreen(page, services)
        await _start(screen)
        during_lesson = set(_keys_under(screen))

        screen._open_zoom()

        during_zoom = set(_keys_under(screen))
        assert {"practice.bar", "practice.body"} <= during_lesson & during_zoom

    async def test_the_progress_bar_is_the_same_bar_from_question_to_question(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)

        await _start(screen)

        assert "practice.progress" in _keys_under(screen)


class TestWhatUnfoldsInsideAQuestion:
    """A fold is a slot with two states, so it fades rather than appearing."""

    async def test_what_the_unit_covers_unfolds(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        assert _state_of(screen, "practice.body.unit") == "practice.body.unit:shut"

        screen._toggle_unit()

        assert _state_of(screen, "practice.body.unit") == "practice.body.unit:open"

    async def test_the_shut_fold_keeps_its_words_out_of_the_tree(
        self, page: FakePage, services: Services
    ) -> None:
        """A slot needs both states; it does not need to carry both texts."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        assert "Present Continuous" not in rendered(screen)

        screen._toggle_unit()

        assert "Present Continuous" in rendered(screen)

    async def test_the_rule_unfolds_the_same_way(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        await _answer(screen)
        assert _state_of(screen, "practice.foot.rule") == "practice.foot.rule:shut"

        screen._on_toggle_rule()

        assert _state_of(screen, "practice.foot.rule") == "practice.foot.rule:open"

    async def test_a_picture_and_a_note_that_there_is_none_are_two_states(
        self, page: FakePage, services: Services
    ) -> None:
        """One key over both would patch a banner into a picture card."""
        screen = PracticeScreen(page, services)
        await _start(screen)
        assert _state_of(screen, "practice.body.image") == "practice.body.image:picture"

        await screen.start_lesson(2, "Past Tenses")

        assert _state_of(screen, "practice.body.image") == "practice.body.image:none"


class TestTheFootMorphs:
    """The bar and the sheet are one surface wearing two looks."""

    async def test_the_bar_and_the_sheet_are_the_same_slot(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        bar = screen.controls[-1]

        await _answer(screen)

        assert bar.key == screen.controls[-1].key == "screen.foot"

    async def test_the_surface_is_what_changes_between_them(
        self, page: FakePage, services: Services
    ) -> None:
        """Its colour, its corners and its padding are what the client tweens."""
        screen = PracticeScreen(page, services)
        await _start(screen)
        bar: Any = screen.controls[-1]

        await _answer(screen)
        raised: Any = screen.controls[-1]

        assert bar.bgcolor != raised.bgcolor
        assert bar.border_radius.top_left != raised.border_radius.top_left
        assert bar.animate is not None
        assert raised.animate is not None

    async def test_each_thing_the_foot_says_is_a_state_of_its_own(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        states = [_state_of(screen.controls[-1], "screen.foot.body")]

        await _answer(screen)
        states.append(_state_of(screen.controls[-1], "screen.foot.body"))
        screen.request_leave()
        states.append(_state_of(screen.controls[-1], "screen.foot.body"))

        assert states == [
            "screen.foot.body:actions",
            "screen.foot.body:verdict:right",
            "screen.foot.body:leaving",
        ]

    async def test_a_wrong_answer_and_a_revealed_one_read_differently(
        self, page: FakePage, wrong_services: Services
    ) -> None:
        screen = PracticeScreen(page, wrong_services)
        await _start(screen)

        await _answer(screen, "did")

        assert (
            _state_of(screen.controls[-1], "screen.foot.body")
            == "screen.foot.body:verdict:wrong"
        )

    async def test_the_foot_drops_what_is_leaving_rather_than_holding_it(
        self, page: FakePage, services: Services
    ) -> None:
        """A bar and a sheet are nothing like the same height."""
        screen = PracticeScreen(page, services)
        await _start(screen)

        region = _region(screen.controls[-1], "screen.foot.body")

        assert region.reverse_duration == motion.LEAVE_AT_ONCE


class TestTheAnswerFieldSurvivesBeingRebuilt:
    """Flet freezes what it mounts in a keyed pass, so the field is rebuilt."""

    async def test_the_field_is_a_new_control_on_every_render(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        before = screen._answer

        screen.repaint()

        assert screen._answer is not before

    async def test_it_keeps_its_key_so_the_client_keeps_the_field(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)

        screen.repaint()

        assert screen._answer.key == "practice.answer"

    async def test_it_keeps_what_was_typed(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        screen._answer.value = "half a sentence"

        screen._toggle_unit()

        assert screen._answer.value == "half a sentence"

    async def test_locking_it_is_a_property_the_client_can_animate(
        self, page: FakePage, services: Services
    ) -> None:
        screen = PracticeScreen(page, services)
        await _start(screen)
        assert screen._answer.read_only is False

        await _answer(screen)

        assert screen._answer.read_only is True
        assert screen._answer.fill_color is not None

    async def test_the_next_question_arrives_with_an_empty_field(
        self, page: FakePage, services: Services
    ) -> None:
        """Emptying it must not be an assignment to a control that may be frozen."""
        screen = PracticeScreen(page, services)
        await _start(screen)
        await _answer(screen)

        await screen._on_continue()

        assert screen._answer.value == ""


class TestTheOtherScreensAnimateTheirWaiting:
    def test_the_home_notice_is_a_slot_in_both_of_its_states(self) -> None:
        view = HomeView(on_start=lambda *_: None, on_open_settings=lambda: None)

        with_problem = view.build(HomeState(problem="No API key"))
        without = view.build(HomeState())

        assert _state_of(with_problem, "home.notice") == "home.notice:problem"
        assert _state_of(without, "home.notice") == "home.notice:ready"

    def test_each_topic_card_is_named_by_its_topic(self) -> None:
        view = HomeView(on_start=lambda *_: None)
        state = HomeState(topics=(Topic(id=7, name="Present Tenses", unit_count=3),))

        built = view.build(state)

        assert "home.topics.7" in _keys_under(built)

    async def test_testing_the_connection_is_one_slot_with_three_states(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)
        assert _state_of(screen, "settings.check") == "settings.check:idle"

        screen._checking = True
        screen.render()
        assert _state_of(screen, "settings.check") == "settings.check:waiting"

        screen._checking = False
        screen._check_result = ("It answered.", True)
        screen.render()

        assert _state_of(screen, "settings.check") == "settings.check:answered"

    async def test_fetching_the_catalogue_swaps_the_chevron_for_a_spinner(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)
        region = "settings.model.trailing"
        assert _state_of(screen, region) == f"{region}:ready"

        screen._loading_models = True
        screen.render()

        assert _state_of(screen, region) == f"{region}:loading"

    async def test_the_settings_panels_are_named_and_named_once_each(
        self, page: FakePage, services: Services
    ) -> None:
        screen = SettingsScreen(page, services)

        keys = [shown.key for shown in screen.controls]

        assert all(key is not None for key in keys)
        assert len(set(keys)) == len(keys)

    async def test_a_weekly_bar_has_a_height_to_grow_to(
        self, page: FakePage, services: Services
    ) -> None:
        """It is the one figure on the screen whose size can be animated."""
        await services.stats.record(
            Attempt(
                topic_name="Present Tenses",
                unit_number=1,
                exercise_id="1.1",
                question_id="2",
                is_correct=True,
            )
        )
        screen = StatsScreen(page, services)
        await screen.reload()

        bars = [
            control
            for key, control in _keys_under(screen).items()
            if key.endswith(".bar")
        ]

        assert len(bars) == 7
        assert all(bar.animate is not None for bar in bars)


class TestTheMotionRulesHoldEverywhere:
    """Two rules the whole app has to keep, checked over every screen it draws."""

    @staticmethod
    async def _every_state(page: FakePage, services: Services) -> list[Any]:
        """Return each screen of the app, in every state it can be drawn in."""
        app = PracticeApp(page, services)
        await app.start()
        drawn: list[Any] = [app.stats, app.settings, app.practice.controls[:]]

        await app.practice.start_lesson(1, "Present Tenses")
        drawn.append(app.practice.controls[:])
        app.practice._open_zoom()
        drawn.append(app.practice.controls[:])
        app.practice._close_zoom()
        await _answer(app.practice)
        drawn.append(app.practice.controls[:])
        app.practice.request_leave()
        drawn.append(app.practice.controls[:])
        app.practice._stay()
        await app.practice._on_continue()
        drawn.append(app.practice.controls[:])
        return drawn

    async def test_nothing_animates_a_property_without_a_key_to_keep_it(
        self, page: FakePage, services: Services
    ) -> None:
        """An unkeyed control is remounted, so its animation never runs."""
        for drawn in await self._every_state(page, services):
            offenders = _animated_without_keys(drawn)
            assert not offenders, [type(node).__name__ for node in offenders]

    async def test_no_two_siblings_are_given_the_same_key(
        self, page: FakePage, services: Services
    ) -> None:
        """Two siblings sharing a key is a reconciliation the client gets wrong."""
        for drawn in await self._every_state(page, services):
            assert _duplicate_sibling_keys(drawn) == []
