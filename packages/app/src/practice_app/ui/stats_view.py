"""The progress screen.

Everything here is derived from the attempt rows on each visit, so the screen
is a pure function of :class:`~practice_app.stats.StatsSummary` — which is what
makes it worth reading: no counter can drift out of step with the answers.
"""

import flet as ft

from practice_app.services import Services
from practice_app.stats import DayStat, StatsSummary, TopicStat
from practice_app.ui import motion
from practice_app.ui.components import (
    SCROLL,
    STRETCH,
    confirm_dialog,
    hint,
    inline_action,
    panel,
    placeholder,
    progress_track,
    section_title,
    show_snack,
    stat_tile,
)
from practice_app.ui.page import DialogPage
from practice_app.ui.screen import Screen
from practice_app.ui.theme import GAP, GAP_LARGE, GAP_SMALL, RADIUS, RADIUS_SMALL

__all__ = ["StatsScreen"]

# The panels, named so a reload updates them and the bars grow, not jump.
_PANEL_KEYS = (
    "stats.hero",
    "stats.streaks",
    "stats.week",
    "stats.topics",
    "stats.footer",
)
_WEEK_ROW_KEY = "stats.week.row"

_MAX_BAR_HEIGHT = 72
_MIN_BAR_HEIGHT = 4
_TOP_TOPICS = 8

# Where the accuracy bar changes colour: comfortable, shaky, and needs work.
_STRONG_ACCURACY = 0.8
_FAIR_ACCURACY = 0.5


def _accuracy_color(accuracy: float, attempts: int) -> str:
    """Return the colour that stands for an accuracy.

    Args:
        accuracy: The share correct, from 0 to 1.
        attempts: How many answers it is based on; none means no colour.

    Returns:
        A theme colour role.
    """
    if attempts == 0:
        return ft.Colors.SURFACE_CONTAINER_HIGHEST
    if accuracy >= _STRONG_ACCURACY:
        return ft.Colors.PRIMARY
    if accuracy >= _FAIR_ACCURACY:
        return ft.Colors.TERTIARY
    return ft.Colors.ERROR


class StatsScreen(Screen):
    """How the practice is going: accuracy, streaks, the week, the topics."""

    tab_title = "Progress"
    tab_label = "Progress"
    tab_icon = ft.Icons.INSIGHTS_ROUNDED

    def __init__(self, page: DialogPage, services: Services) -> None:
        """Build the screen.

        Args:
            page: The page, for the reset confirmation and snack bars.
            services: The app's dependencies.
        """
        self._page = page
        self._services = services
        self._summary = StatsSummary()

        super().__init__(
            spacing=GAP, scroll=SCROLL, expand=True, horizontal_alignment=STRETCH
        )
        self.render()

    # --- Rendering ---

    def render(self) -> None:
        """Rebuild the screen from the held summary."""
        summary = self._summary
        if summary.is_empty:
            self.controls = [
                placeholder(
                    icon=ft.Icons.INSIGHTS_ROUNDED,
                    title="No progress yet",
                    message=(
                        "Answer a question on the Practice tab and your "
                        "accuracy, streaks and topics show up here."
                    ),
                    expand=True,
                )
            ]
            return

        panels = (
            self._hero(summary),
            self._streaks(summary),
            self._week(summary),
            self._topics(summary),
            self._footer(summary),
        )
        self.controls = [
            motion.keyed(panel, key)
            for panel, key in zip(panels, _PANEL_KEYS, strict=True)
        ]

    def _hero(self, summary: StatsSummary) -> ft.Control:
        """Return the headline accuracy card.

        Args:
            summary: The figures to show.

        Returns:
            The card.
        """
        percent = round(summary.accuracy * 100)
        return ft.Container(
            content=ft.Column(
                controls=[
                    section_title("Accuracy"),
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"{percent}%",
                                size=44,
                                weight=ft.FontWeight.W_700,
                                color=ft.Colors.ON_PRIMARY_CONTAINER,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        f"{summary.correct} correct",
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                                    ),
                                    ft.Text(
                                        f"{summary.wrong} to revisit",
                                        size=12,
                                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                                    ),
                                ],
                                spacing=2,
                                tight=True,
                                expand=True,
                            ),
                        ],
                        spacing=GAP,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    progress_track(
                        summary.accuracy,
                        height=8,
                        bgcolor=ft.Colors.with_opacity(0.25, ft.Colors.PRIMARY),
                        expand=False,
                    ),
                    ft.Text(
                        f"{summary.total} answers over "
                        f"{summary.days_practised} "
                        f"day{'' if summary.days_practised == 1 else 's'}",
                        size=12,
                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                    ),
                ],
                spacing=GAP_SMALL,
                tight=True,
                horizontal_alignment=STRETCH,
            ),
            padding=GAP + 2,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            border_radius=RADIUS,
        )

    def _streaks(self, summary: StatsSummary) -> ft.Control:
        """Return the run of small figures under the accuracy card.

        Args:
            summary: The figures to show.

        Returns:
            Four tiles, two to a row.
        """
        today = summary.today
        tiles = (
            stat_tile(
                str(summary.current_streak),
                "in a row now",
                ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                color=ft.Colors.TERTIARY,
            ),
            stat_tile(
                str(summary.best_streak),
                "best run",
                ft.Icons.EMOJI_EVENTS_ROUNDED,
            ),
            stat_tile(
                f"{today.correct}/{today.attempts}",
                "today",
                ft.Icons.TASK_ALT_ROUNDED,
            ),
            stat_tile(
                str(summary.day_streak),
                "day streak",
                ft.Icons.CALENDAR_MONTH_ROUNDED,
            ),
        )
        # Two by two: four across 360dp breaks "in a row now" into three lines.
        return ft.Column(
            controls=[
                ft.Row(controls=list(pair), spacing=GAP_SMALL)
                for pair in (tiles[:2], tiles[2:])
            ],
            spacing=GAP_SMALL,
            tight=True,
            horizontal_alignment=STRETCH,
        )

    def _week(self, summary: StatsSummary) -> ft.Control:
        """Return the day-by-day chart of the last week.

        Args:
            summary: The figures to show.

        Returns:
            The panel.
        """
        busiest = max((day.attempts for day in summary.recent_days), default=0)
        return panel(
            motion.keyed(
                ft.Row(
                    controls=[self._bar(day, busiest) for day in summary.recent_days],
                    spacing=GAP_SMALL,
                    vertical_alignment=ft.CrossAxisAlignment.END,
                ),
                _WEEK_ROW_KEY,
            ),
            title="Last 7 days",
            spacing=GAP,
        )

    def _bar(self, day: DayStat, busiest: int) -> ft.Control:
        """Return one column of the weekly chart.

        Args:
            day: The day to draw.
            busiest: The highest attempt count in the window, which sets the
                scale so a quiet week is not drawn as a flat line.

        Returns:
            The bar, its weekday letter, and its count.
        """
        share = day.attempts / busiest if busiest else 0
        height = max(_MIN_BAR_HEIGHT, round(share * _MAX_BAR_HEIGHT))

        # STRETCH is what gives the bar a width; anything else shrink-wraps it away.
        return motion.keyed(
            ft.Column(
                controls=[
                    ft.Text(
                        str(day.attempts) if day.attempts else "",
                        size=10,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    # Keyed and animated, so the day's bar grows to its new height.
                    motion.keyed(
                        ft.Container(
                            height=height,
                            bgcolor=_accuracy_color(day.accuracy, day.attempts),
                            border_radius=RADIUS_SMALL,
                            animate=motion.SETTLE_SLOW,
                            tooltip=(
                                f"{day.day.isoformat()}: {day.correct}/{day.attempts}"
                                if day.attempts
                                else f"{day.day.isoformat()}: nothing"
                            ),
                        ),
                        f"{_WEEK_ROW_KEY}.{day.day.isoformat()}.bar",
                    ),
                    ft.Text(
                        day.day.strftime("%a")[0],
                        size=11,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                expand=True,
                tight=True,
            ),
            f"{_WEEK_ROW_KEY}.{day.day.isoformat()}",
        )

    def _topics(self, summary: StatsSummary) -> ft.Control:
        """Return the per-topic breakdown.

        Args:
            summary: The figures to show.

        Returns:
            The panel.
        """
        shown = summary.topics[:_TOP_TOPICS]
        rows: list[ft.Control] = [self._topic_row(topic) for topic in shown]
        if len(summary.topics) > len(shown):
            rows.append(hint(f"and {len(summary.topics) - len(shown)} more topics"))
        return panel(*rows, title="By topic", spacing=GAP)

    def _topic_row(self, topic: TopicStat) -> ft.Control:
        """Return one topic's line.

        Args:
            topic: The topic to show.

        Returns:
            Its name, its bar and its tally.
        """
        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            topic.name,
                            size=13,
                            weight=ft.FontWeight.W_500,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            expand=True,
                        ),
                        ft.Text(
                            f"{topic.correct}/{topic.attempts}",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=GAP_SMALL,
                ),
                progress_track(
                    topic.accuracy,
                    height=6,
                    color=_accuracy_color(topic.accuracy, topic.attempts),
                    expand=False,
                ),
            ],
            spacing=6,
            tight=True,
            horizontal_alignment=STRETCH,
        )

    def _footer(self, summary: StatsSummary) -> ft.Control:
        """Return the practice window and the reset button.

        Args:
            summary: The figures to show.

        Returns:
            The footer.
        """
        span = ""
        if summary.first_day and summary.last_day:
            span = (
                f"First answer {summary.first_day.isoformat()}, "
                f"latest {summary.last_day.isoformat()}."
            )

        return ft.Container(
            content=ft.Column(
                controls=[
                    hint(span),
                    inline_action(
                        "Reset progress",
                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                        on_click=self._confirm_reset,
                        danger=True,
                    ),
                ],
                spacing=GAP_SMALL,
                horizontal_alignment=STRETCH,
                tight=True,
            ),
            padding=ft.Padding.only(bottom=GAP_LARGE),
        )

    # --- Events ---

    def _confirm_reset(self) -> None:
        """Ask before deleting the progress history."""
        self._page.show_dialog(
            confirm_dialog(
                self._page,
                title="Reset progress?",
                message="Every recorded answer is deleted. This cannot be undone.",
                confirm="Reset",
                on_confirm=self._reset,
                danger=True,
            )
        )

    async def _reset(self) -> None:
        """Delete the progress history and redraw."""
        self._page.pop_dialog()
        await self._services.stats.reset()
        await self.reload()
        show_snack(self._page, "Progress reset.")

    async def reload(self) -> None:
        """Reload the figures and redraw."""
        self._summary = await self._services.stats.summary()
        self.repaint()
