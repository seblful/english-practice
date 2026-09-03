"""The screen between lessons: what today looks like, and what to practise.

This is the course list of a studying app rather than a menu. The card at the
top is the one thing to do next — a lesson — and under it the book's topics are
laid out as the runs they lead to, each carrying how the user has done on it so
far. Picking a topic is a tap on the topic, not a trip through a dialog.

The view only draws. Everything it needs arrives in a :class:`HomeState`, and
everything a tap does leaves through one callback, so what it renders can be
asserted without a session, a lesson or a network.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import flet as ft
from practice_core.models import Topic

from practice_app.session import LESSON_LENGTH
from practice_app.stats import StatsSummary, TopicStat
from practice_app.ui.components import (
    STRETCH,
    banner,
    hint,
    inline_action,
    pill,
    placeholder,
    primary_action,
    progress_track,
    secondary_action,
    section_title,
)
from practice_app.ui.theme import (
    GAP,
    GAP_LARGE,
    GAP_SMALL,
    RADIUS,
    RADIUS_LARGE,
    RADIUS_SMALL,
)

__all__ = ["MIXED_LESSON_LABEL", "HomeState", "HomeView"]

# What a run across every topic is called on screen.
MIXED_LESSON_LABEL = "Mixed practice"

# Starts a lesson: the topic to draw from, and what to call it.
StartLesson = Callable[[int | None, str], None]


@dataclass(frozen=True, slots=True)
class HomeState:
    """Everything the home screen draws itself from."""

    summary: StatsSummary = field(default_factory=StatsSummary)
    topics: Sequence[Topic] = ()
    topic_stats: Mapping[str, TopicStat] = field(default_factory=dict)
    # The first thing stopping the app from grading, if anything is.
    problem: str | None = None
    # The topic of the last lesson, offered again when there was one.
    last_topic_id: int | None = None
    last_topic_name: str | None = None


class HomeView:
    """Builds the home screen. Holds no state of its own."""

    def __init__(
        self,
        *,
        on_start: StartLesson,
        on_open_settings: Callable[[], None] | None = None,
    ) -> None:
        """Wire the two things a tap here can do.

        Args:
            on_start: Starts a lesson on a topic, or on all of them.
            on_open_settings: Switches to the settings tab. Omitted when there
                is nowhere to switch to, which is what a test usually wants.
        """
        self._on_start = on_start
        self._on_open_settings = on_open_settings

    def build(self, state: HomeState) -> list[ft.Control]:
        """Return the screen, top to bottom.

        Args:
            state: What to draw.

        Returns:
            The setup notice if there is one, today's card, the last topic
            again if there was one, and the topics to pick from.
        """
        children: list[ft.Control] = []

        if state.problem is not None:
            children.append(self._setup_banner(state.problem))

        children.append(self._today_card(state.summary))
        if state.last_topic_id is not None:
            children.append(self._again_button(state))
        children.append(self._topic_list(state))
        # The last card would otherwise end up under the navigation bar.
        children.append(ft.Container(height=GAP_LARGE))
        return children

    # ------------------------------------------------------------------
    # Pieces
    # ------------------------------------------------------------------

    def _setup_banner(self, problem: str) -> ft.Control:
        """Return the notice shown while the app cannot grade yet.

        Args:
            problem: The first thing that is missing.

        Returns:
            The banner, with a shortcut to the settings tab.
        """
        actions: list[ft.Control] = []
        open_settings = self._on_open_settings
        if open_settings is not None:
            actions.append(
                inline_action(
                    "Open settings",
                    icon=ft.Icons.SETTINGS_ROUNDED,
                    # The notice already carries a tint, and an outline drawn
                    # on top of that tint disappears into it.
                    filled=True,
                    on_click=lambda _: open_settings(),
                )
            )
        return banner(
            f"{problem}. You can still practise and reveal answers.",
            icon=ft.Icons.WARNING_AMBER_ROUNDED,
            color=ft.Colors.ON_TERTIARY_CONTAINER,
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
            actions=actions,
        )

    def _today_card(self, summary: StatsSummary) -> ft.Control:
        """Return the card a lesson is started from.

        Args:
            summary: The progress so far.

        Returns:
            The day streak, how much of the daily goal is done, and the one
            button that matters on this screen.
        """
        done = min(summary.today.attempts, LESSON_LENGTH)
        streak = summary.day_streak
        on_hero = ft.Colors.ON_PRIMARY_CONTAINER

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            pill(
                                f"{streak} day streak" if streak else "First day",
                                icon=ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                                color=on_hero,
                                bgcolor=ft.Colors.with_opacity(0.18, on_hero),
                            ),
                            ft.Container(expand=True),
                            ft.Text(
                                f"{done}/{LESSON_LENGTH} today",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=on_hero,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "Daily goal reached" if done >= LESSON_LENGTH else "Today",
                        size=22,
                        weight=ft.FontWeight.W_700,
                        color=on_hero,
                    ),
                    progress_track(
                        done / LESSON_LENGTH,
                        color=ft.Colors.PRIMARY,
                        bgcolor=ft.Colors.with_opacity(0.20, on_hero),
                    ),
                    ft.Text(
                        f"A lesson is {LESSON_LENGTH} questions from Murphy's "
                        "English Grammar in Use.",
                        size=12,
                        color=on_hero,
                    ),
                    ft.Row(
                        controls=[
                            primary_action(
                                "Start a lesson",
                                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                on_click=lambda _: self._on_start(
                                    None, MIXED_LESSON_LABEL
                                ),
                            )
                        ]
                    ),
                ],
                spacing=GAP_SMALL,
                tight=True,
                horizontal_alignment=STRETCH,
            ),
            padding=GAP + 2,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            border_radius=RADIUS_LARGE,
        )

    def _again_button(self, state: HomeState) -> ft.Control:
        """Return the shortcut back to the topic just practised.

        Args:
            state: What to draw.

        Returns:
            The button, in a row so that it fills the width.
        """
        topic_id = state.last_topic_id
        name = state.last_topic_name or MIXED_LESSON_LABEL
        return ft.Row(
            controls=[
                secondary_action(
                    f"Again: {name}",
                    icon=ft.Icons.REPLAY_ROUNDED,
                    on_click=lambda _: self._on_start(topic_id, name),
                    expand=True,
                )
            ]
        )

    def _topic_list(self, state: HomeState) -> ft.Control:
        """Return the topics, as lessons waiting to be started.

        Args:
            state: What to draw.

        Returns:
            One card per topic, or a note when the book could not be read.
        """
        if not state.topics:
            return placeholder(
                icon=ft.Icons.CATEGORY_ROUNDED,
                title="No topics to show",
                message=(
                    "The bundled book could not be read, so there is nothing "
                    "to practise yet."
                ),
                expand=True,
            )

        return ft.Column(
            controls=[
                section_title("Practise a topic"),
                *(
                    self._topic_card(topic, state.topic_stats.get(topic.name))
                    for topic in state.topics
                ),
            ],
            spacing=GAP_SMALL,
            tight=True,
            horizontal_alignment=STRETCH,
        )

    def _topic_card(self, topic: Topic, stat: TopicStat | None) -> ft.Control:
        """Return one topic's card.

        Args:
            topic: The topic to offer.
            stat: How the user has done on it, when they have tried it.

        Returns:
            Its name, its size, and its tally so far.
        """
        units = f"{topic.unit_count} unit{'' if topic.unit_count == 1 else 's'}"
        subtitle = (
            units if stat is None else f"{units} - {stat.correct}/{stat.attempts}"
        )

        rows: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.MENU_BOOK_ROUNDED,
                            size=18,
                            color=ft.Colors.ON_SECONDARY_CONTAINER,
                        ),
                        padding=GAP_SMALL + 2,
                        bgcolor=ft.Colors.SECONDARY_CONTAINER,
                        border_radius=RADIUS_SMALL,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                topic.name,
                                weight=ft.FontWeight.W_600,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            hint(subtitle),
                        ],
                        spacing=2,
                        tight=True,
                        expand=True,
                    ),
                    ft.Icon(
                        ft.Icons.CHEVRON_RIGHT_ROUNDED,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        size=20,
                    ),
                ],
                spacing=GAP_SMALL + 2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        if stat is not None:
            rows.append(progress_track(stat.accuracy, height=5))

        return ft.Container(
            content=ft.Column(
                controls=rows,
                spacing=GAP_SMALL,
                tight=True,
                horizontal_alignment=STRETCH,
            ),
            padding=GAP_SMALL + 4,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=RADIUS,
            ink=True,
            on_click=lambda _, chosen=topic: self._on_start(chosen.id, chosen.name),
        )
