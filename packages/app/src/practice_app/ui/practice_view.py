"""The practice screen: draw an exercise, answer it, see how you did.

This is the bot's flow with the chat taken out. There is no transcript and no
follow-up conversation: one question is on screen, it gets one answer, and the
book's answer and rule follow. Everything the user needs is therefore visible
at once rather than scrolled back to.
"""

from collections.abc import Callable, Sequence

import flet as ft
from practice_core.errors import ContentError, PracticeError
from practice_core.feedback import (
    full_answer_text,
    short_answer_text,
    to_markdown,
    verdict_phrase,
)
from practice_core.models import Topic

from practice_app.services import Services
from practice_app.session import ActiveExercise, PracticeSession
from practice_app.stats import Attempt
from practice_app.ui.components import (
    banner,
    hint,
    panel,
    pill,
    placeholder,
    push,
    show_snack,
)
from practice_app.ui.page import DialogPage
from practice_app.ui.theme import GAP, GAP_LARGE, GAP_SMALL, RADIUS, RADIUS_SMALL

__all__ = ["PracticeScreen"]

RANDOM_TOPIC_LABEL = "Random"

_NO_EXERCISES = "No exercises found for this topic. Try another one."
_EMPTY_ANSWER = "Type your answer first."
_GRADING_FAILED = "Could not grade that. Here is the book's answer."


class PracticeScreen(ft.Column):
    """One exercise at a time, and what happened to the last answer."""

    def __init__(
        self,
        page: DialogPage,
        services: Services,
        *,
        on_open_settings: Callable[[], None] | None = None,
    ) -> None:
        """Build the screen.

        Args:
            page: The page, for dialogs and snack bars.
            services: The app's dependencies.
            on_open_settings: Switches to the settings tab, used by the "not
                configured yet" banner.
        """
        self._page = page
        self._services = services
        self._on_open_settings = on_open_settings
        self._session = PracticeSession()
        self._busy = False
        self._topics: tuple[Topic, ...] = ()

        self._answer = ft.TextField(
            hint_text="Type your answer",
            multiline=True,
            shift_enter=True,
            min_lines=1,
            max_lines=4,
            filled=True,
            border_radius=RADIUS_SMALL,
            autocorrect=False,
            capitalization=ft.TextCapitalization.NONE,
            on_submit=self._on_check,
        )

        super().__init__(
            spacing=GAP,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> None:
        """Rebuild the screen from the current state."""
        children: list[ft.Control] = []

        problems = self._services.config.missing()
        if problems:
            children.append(self._setup_banner(problems[0]))

        active = self._session.active
        if active is None:
            children.append(self._start_panel())
        else:
            children.extend(self._exercise_panels(active))

        self.controls = children

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
                ft.FilledButton(
                    content="Open settings",
                    icon=ft.Icons.SETTINGS_ROUNDED,
                    on_click=lambda _: open_settings(),
                )
            )
        return banner(
            f"{problem}. You can still draw exercises and reveal answers.",
            icon=ft.Icons.WARNING_AMBER_ROUNDED,
            color=ft.Colors.ON_TERTIARY_CONTAINER,
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
            actions=actions,
        )

    def _start_panel(self) -> ft.Control:
        """Return the block that starts a practice run.

        Returns:
            The placeholder with one button per way to pick a topic.
        """
        actions: list[ft.Control] = [
            ft.FilledButton(
                content="Random exercise",
                icon=ft.Icons.CASINO_ROUNDED,
                on_click=self._on_random,
            ),
            ft.OutlinedButton(
                content="Choose a topic",
                icon=ft.Icons.CATEGORY_ROUNDED,
                on_click=self._on_choose_topic,
            ),
        ]
        if self._session.has_previous_topic:
            actions.append(
                ft.TextButton(
                    content=f"Again: {self._session.last_topic_name}",
                    icon=ft.Icons.REFRESH_ROUNDED,
                    on_click=self._on_same_topic,
                )
            )

        return placeholder(
            icon=ft.Icons.SCHOOL_ROUNDED,
            title="Ready to practise?",
            message=(
                "Pick a topic and I will draw an exercise from Murphy's "
                "English Grammar in Use."
            ),
            actions=actions,
        )

    def _exercise_panels(self, active: ActiveExercise) -> list[ft.Control]:
        """Return everything shown while an exercise is open.

        Args:
            active: The exercise in front of the user.

        Returns:
            The controls, top to bottom.
        """
        children: list[ft.Control] = [
            self._header(active),
            self._image_card(active),
        ]

        if active.is_revealed:
            children.extend(self._result_panels(active))
        else:
            children.extend([self._answer, self._answer_actions()])

        return children

    def _header(self, active: ActiveExercise) -> ft.Control:
        """Return the topic, unit and question line above the exercise.

        Args:
            active: The exercise in front of the user.

        Returns:
            The header.
        """
        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        pill(active.topic_name, icon=ft.Icons.CATEGORY_ROUNDED),
                        ft.Container(
                            content=pill(
                                f"Unit {active.exercise.unit.unit_number}",
                                icon=ft.Icons.MENU_BOOK_ROUNDED,
                                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ink=True,
                            border_radius=RADIUS_SMALL,
                            on_click=lambda _: self._show_unit(active),
                            tooltip="What this unit covers",
                        ),
                    ],
                    spacing=GAP_SMALL,
                    wrap=True,
                    run_spacing=GAP_SMALL,
                ),
                ft.Text(
                    f"Question {active.question.question_id}",
                    size=24,
                    weight=ft.FontWeight.W_700,
                ),
                hint(
                    "Answer in your own words - the grammar is what counts."
                    if active.question.is_open_ended
                    else "Type the missing words, or the whole sentence."
                ),
            ],
            spacing=GAP_SMALL,
            tight=True,
        )

    def _image_card(self, active: ActiveExercise) -> ft.Control:
        """Return the exercise image, or a note that there is none.

        Args:
            active: The exercise in front of the user.

        Returns:
            The image card.
        """
        if active.image is None:
            return banner(
                "This exercise has no picture in the database.",
                icon=ft.Icons.IMAGE_ROUNDED,
                color=ft.Colors.ON_TERTIARY_CONTAINER,
                bgcolor=ft.Colors.TERTIARY_CONTAINER,
            )

        return ft.Container(
            content=ft.Stack(
                controls=[
                    ft.Image(
                        src=active.image,
                        fit=ft.BoxFit.FIT_WIDTH,
                        border_radius=RADIUS,
                        gapless_playback=True,
                    ),
                    ft.Container(
                        content=ft.Icon(
                            ft.Icons.ZOOM_IN_ROUNDED,
                            size=18,
                            color=ft.Colors.ON_INVERSE_SURFACE,
                        ),
                        padding=6,
                        bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.INVERSE_SURFACE),
                        border_radius=RADIUS_SMALL,
                        right=GAP_SMALL,
                        bottom=GAP_SMALL,
                    ),
                ]
            ),
            padding=GAP_SMALL,
            bgcolor=ft.Colors.WHITE,
            border_radius=RADIUS,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=lambda _: self._zoom_image(active),
            tooltip="Tap to zoom",
        )

    def _answer_actions(self) -> ft.Control:
        """Return the buttons under the answer field.

        Returns:
            A progress row while grading, the buttons otherwise.
        """
        if self._busy:
            return ft.Row(
                controls=[
                    ft.ProgressRing(width=18, height=18, stroke_width=2),
                    hint("Grading your answer..."),
                ],
                spacing=GAP_SMALL + 2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        return ft.Row(
            controls=[
                ft.FilledButton(
                    content="Check answer",
                    icon=ft.Icons.TASK_ALT_ROUNDED,
                    on_click=self._on_check,
                    expand=True,
                ),
                ft.OutlinedButton(
                    content="Reveal",
                    icon=ft.Icons.VISIBILITY_ROUNDED,
                    tooltip="Show the book's answer without grading",
                    on_click=self._on_reveal,
                ),
            ],
            spacing=GAP_SMALL,
        )

    def _result_panels(self, active: ActiveExercise) -> list[ft.Control]:
        """Return the verdict, the answers, the rule and what to do next.

        Args:
            active: The exercise that was just answered.

        Returns:
            The controls, top to bottom.
        """
        children: list[ft.Control] = []

        evaluation = active.evaluation
        if evaluation is not None:
            correct = evaluation.is_correct
            children.append(
                banner(
                    verdict_phrase(correct),
                    icon=(
                        ft.Icons.CHECK_CIRCLE_ROUNDED
                        if correct
                        else ft.Icons.CANCEL_ROUNDED
                    ),
                    color=(
                        ft.Colors.ON_PRIMARY_CONTAINER
                        if correct
                        else ft.Colors.ON_ERROR_CONTAINER
                    ),
                    bgcolor=(
                        ft.Colors.PRIMARY_CONTAINER
                        if correct
                        else ft.Colors.ERROR_CONTAINER
                    ),
                )
            )

        typed = (self._answer.value or "").strip()
        if typed:
            children.append(panel(ft.Text(typed, selectable=True), title="Your answer"))

        answers = active.revealed_answers
        if answers:
            children.append(
                panel(
                    ft.Markdown(
                        to_markdown(short_answer_text(answers)),
                        selectable=True,
                    ),
                    title="Correct answer",
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                )
            )
            children.append(
                panel(
                    # A markdown renderer reads a single newline as a soft
                    # wrap, so two answers need a blank line between them.
                    ft.Markdown(
                        full_answer_text(answers, separator="\n\n"),
                        selectable=True,
                    ),
                    title="Full answer",
                )
            )
        elif active.question.is_open_ended:
            children.append(
                panel(
                    hint("This question is open-ended, so the book prints no answer."),
                    title="Correct answer",
                )
            )

        rule = active.question.rule
        if self._services.config.show_rules and rule:
            children.append(
                panel(
                    ft.Markdown(to_markdown(rule), selectable=True),
                    title=f"Rule {active.unit_reference}",
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                )
            )

        children.append(self._next_actions())
        return children

    def _next_actions(self) -> ft.Control:
        """Return the buttons that start the next exercise.

        Returns:
            The row of buttons.
        """
        buttons: list[ft.Control] = [
            ft.FilledButton(
                content="Next exercise",
                icon=ft.Icons.SKIP_NEXT_ROUNDED,
                on_click=self._on_next,
                expand=True,
            )
        ]
        if self._session.has_previous_topic:
            buttons.append(
                ft.OutlinedButton(
                    content="Random",
                    icon=ft.Icons.CASINO_ROUNDED,
                    on_click=self._on_random,
                )
            )
        buttons.append(
            ft.OutlinedButton(
                content="Topics",
                icon=ft.Icons.CATEGORY_ROUNDED,
                on_click=self._on_choose_topic,
            )
        )

        return ft.Container(
            content=ft.Row(
                controls=buttons, spacing=GAP_SMALL, wrap=True, run_spacing=GAP_SMALL
            ),
            padding=ft.Padding.only(bottom=GAP_LARGE),
        )

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _show_unit(self, active: ActiveExercise) -> None:
        """Show which unit the exercise came from.

        Args:
            active: The exercise in front of the user.
        """
        unit = active.exercise.unit
        self._page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Unit {unit.unit_number}"),
                content=ft.Text(unit.title),
                actions=[
                    ft.TextButton("Close", on_click=lambda _: self._page.pop_dialog())
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                shape=ft.RoundedRectangleBorder(radius=RADIUS),
            )
        )

    def _zoom_image(self, active: ActiveExercise) -> None:
        """Open the exercise image in a pinch-zoomable view.

        Args:
            active: The exercise in front of the user.
        """
        if active.image is None:  # pragma: no cover - the card is not tappable
            return
        self._page.show_dialog(
            ft.AlertDialog(
                content=ft.Container(
                    content=ft.InteractiveViewer(
                        content=ft.Image(src=active.image, fit=ft.BoxFit.CONTAIN),
                        min_scale=1,
                        max_scale=6,
                    ),
                    bgcolor=ft.Colors.WHITE,
                    border_radius=RADIUS_SMALL,
                    height=420,
                ),
                content_padding=GAP_SMALL,
                inset_padding=GAP_SMALL,
                actions=[
                    ft.TextButton("Close", on_click=lambda _: self._page.pop_dialog())
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                shape=ft.RoundedRectangleBorder(radius=RADIUS),
            )
        )

    def _topic_dialog(self, topics: Sequence[Topic]) -> ft.AlertDialog:
        """Build the topic chooser.

        Args:
            topics: The topics to offer.

        Returns:
            The dialog.
        """
        rows: list[ft.Control] = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(topic.name, weight=ft.FontWeight.W_600),
                                hint(
                                    f"{topic.unit_count} "
                                    f"unit{'' if topic.unit_count == 1 else 's'}"
                                ),
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
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=GAP_SMALL + 4, vertical=10),
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=RADIUS_SMALL,
                ink=True,
                on_click=lambda _, chosen=topic: self._page.run_task(
                    self._pick_topic, chosen
                ),
            )
            for topic in topics
        ]

        return ft.AlertDialog(
            title=ft.Text("Choose a topic"),
            content=ft.Container(
                width=560,
                height=460,
                content=ft.ListView(controls=rows, spacing=GAP_SMALL - 2),
            ),
            content_padding=ft.Padding.symmetric(horizontal=GAP, vertical=GAP_SMALL),
            inset_padding=GAP,
            actions=[
                ft.TextButton("Close", on_click=lambda _: self._page.pop_dialog())
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS),
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def _on_random(self) -> None:
        """Draw from every topic."""
        await self.draw(None, RANDOM_TOPIC_LABEL)

    async def _on_same_topic(self) -> None:
        """Draw from the topic the user last practised."""
        await self.draw(
            self._session.last_topic_id,
            self._session.last_topic_name or RANDOM_TOPIC_LABEL,
        )

    async def _on_next(self) -> None:
        """Draw another exercise from wherever the last one came from."""
        active = self._session.active
        topic_id = active.topic_id if active else self._session.last_topic_id
        name = active.topic_name if active else self._session.last_topic_name
        await self.draw(topic_id, name or RANDOM_TOPIC_LABEL)

    async def _on_choose_topic(self) -> None:
        """Show the topic list, loading it once."""
        if not self._topics:
            try:
                self._topics = tuple(await self._services.content.list_topics())
            except ContentError as exc:
                show_snack(self._page, str(exc), error=True)
                return
        self._page.show_dialog(self._topic_dialog(self._topics))

    async def _pick_topic(self, topic: Topic) -> None:
        """Close the chooser and draw from the chosen topic.

        Args:
            topic: The topic the user tapped.
        """
        self._page.pop_dialog()
        await self.draw(topic.id, topic.name)

    async def _on_reveal(self) -> None:
        """Show the book's answer without asking the model anything."""
        active = self._session.active
        if active is None:  # pragma: no cover - the button is not shown
            return
        active.ungraded = True
        self.render()
        push(self)

    async def _on_check(self) -> None:
        """Grade what the user typed."""
        active = self._session.active
        if active is None or self._busy:  # pragma: no cover - guarded by the UI
            return

        typed = (self._answer.value or "").strip()
        if not typed:
            show_snack(self._page, _EMPTY_ANSWER)
            return

        self._busy = True
        self.render()
        push(self)

        try:
            evaluation = await self._services.grader.grade(
                question=active.question,
                user_input=typed,
                answers=active.answers,
                topic_name=active.topic_name,
                image=active.image,
            )
        except PracticeError as exc:
            active.ungraded = True
            show_snack(self._page, f"{_GRADING_FAILED} {exc}", error=True)
        else:
            active.evaluation = evaluation
            await self._services.stats.record(
                Attempt(
                    topic_name=active.topic_name,
                    unit_number=active.exercise.unit.unit_number,
                    exercise_id=active.exercise.exercise_id,
                    question_id=active.question.question_id,
                    is_correct=evaluation.is_correct,
                )
            )
        finally:
            self._busy = False
            self.render()
            push(self)

    # ------------------------------------------------------------------
    # Drawing an exercise
    # ------------------------------------------------------------------

    async def draw(self, topic_id: int | None, topic_name: str) -> None:
        """Draw an exercise and put it on screen.

        Args:
            topic_id: The topic to draw from, or ``None`` for any.
            topic_name: What to call it on screen.
        """
        try:
            drawn = await self._services.content.draw_question(topic_id)
        except ContentError as exc:
            show_snack(self._page, str(exc), error=True)
            return

        if drawn is None:
            show_snack(self._page, _NO_EXERCISES)
            return

        exercise, question, image = drawn
        try:
            answers = await self._services.content.list_answers(question.id)
        except ContentError as exc:  # pragma: no cover - the draw already read the file
            show_snack(self._page, str(exc), error=True)
            return

        self._answer.value = ""
        self._session.start(
            ActiveExercise(
                exercise=exercise,
                question=question,
                topic_id=topic_id,
                topic_name=(
                    topic_name
                    if topic_id is not None
                    else exercise.unit.topic_name or RANDOM_TOPIC_LABEL
                ),
                image=image,
                answers=tuple(answers),
            )
        )
        self.render()
        push(self)

    def refresh(self) -> None:
        """Re-render after a settings change, which may hide the setup banner."""
        self.render()
        push(self)
