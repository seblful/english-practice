"""The practice screen: a lesson, one question at a time.

The shape here is a studying app's rather than a conversation's. A lesson is a
fixed run of questions: a bar across the top says how far along it is, the
question owns the middle of the screen, the action sits under the thumb, and
the verdict arrives as a sheet over the bottom.

That last part is the point. Nothing accumulates: the question the user just
answered stays exactly where it was, with their own words still in the field
beside the book's, instead of scrolling away above a growing transcript of
panels. What is on screen is the question being worked on, and that is all.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft
from practice_core.errors import ContentError, PracticeError
from practice_core.feedback import (
    full_answer_text,
    short_answer_text,
    to_markdown,
    verdict_phrase,
)

from practice_app.services import Services
from practice_app.session import ActiveExercise, Lesson, PracticeSession
from practice_app.stats import Attempt, StatsSummary, TopicStat
from practice_app.ui.components import (
    action_bar,
    banner,
    hint,
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
    text_field,
)
from practice_app.ui.home_view import HomeState, HomeView
from practice_app.ui.page import DialogPage
from practice_app.ui.theme import (
    GAP,
    GAP_SMALL,
    GAP_TINY,
    RADIUS,
    RADIUS_SMALL,
)

if TYPE_CHECKING:  # pragma: no cover - the topics are only ever annotated here
    from practice_core.models import Topic

__all__ = ["RANDOM_TOPIC_LABEL", "PracticeScreen"]

# What a question drawn from every topic is filed under when the book does not
# say which topic its unit belongs to.
RANDOM_TOPIC_LABEL = "Random"

_REVEALED_HEADLINE = "Here is the answer"

_NO_EXERCISES = "No exercises found for this topic. Try another one."
_EMPTY_ANSWER = "Type your answer first."
_GRADING_FAILED = "Could not grade that. Here is the book's answer."

# A rule can run to a screenful, and the sheet must not push the question it
# explains off the top of the screen.
_RULE_HEIGHT = 160

# The exercise crops are wide and short -- ten numbered lines across a book
# page -- so a tall frame spends most of itself on blank paper either side of
# the picture and the zoom looks like it did nothing. This is deep enough to
# read a crop in and to pan a magnified one around.
_ZOOM_HEIGHT = 260
_ZOOM_PAN_MARGIN = 80


class PracticeScreen(ft.Column):
    """A lesson: a run of questions, one on screen at a time."""

    def __init__(
        self,
        page: DialogPage,
        services: Services,
        *,
        on_open_settings: Callable[[], None] | None = None,
        on_lesson_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Build the screen.

        Args:
            page: The page, for dialogs and snack bars.
            services: The app's dependencies.
            on_open_settings: Switches to the settings tab, used by the "not
                configured yet" notice.
            on_lesson_change: Told whether a lesson is running, so the shell
                can get its chrome out of the way of one.
        """
        self._page = page
        self._services = services
        self._on_lesson_change = on_lesson_change
        self._home = HomeView(
            on_start=self._start_from_home, on_open_settings=on_open_settings
        )
        self._session = PracticeSession()
        self._summary = StatsSummary()
        self._topic_stats: dict[str, TopicStat] = {}
        self._topics: tuple[Topic, ...] = ()
        self._busy = False
        # Drawn once per verdict rather than once per render, so folding the
        # rule open does not re-roll the praise.
        self._verdict = ""
        # Why the model could not be asked, when it could not be. It goes in
        # the sheet rather than a snack bar: a snack floats over the bottom of
        # the screen, which is exactly where the sheet puts the one button
        # that moves the lesson on.
        self._grading_error: str | None = None
        self._rule_open = False

        self._answer = text_field(
            hint_text="Type your answer",
            multiline=True,
            shift_enter=True,
            min_lines=2,
            max_lines=5,
            autocorrect=False,
            capitalization=ft.TextCapitalization.NONE,
            on_submit=self._on_check,
        )

        super().__init__(spacing=0, expand=True)
        self.render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self) -> None:
        """Rebuild the screen from the current state.

        There are three states, and which one is showing is read off the
        session alone: no lesson is the home screen, a lesson with a question
        is the lesson itself, and a lesson whose question has been put down is
        the result.
        """
        lesson = self._session.lesson
        if lesson is None:
            self.controls = [self._scroller(*self._home.build(self._home_state()))]
        elif lesson.active is None:
            self.controls = [
                self._scroller(*self._result_panels(lesson)),
                self._result_actions(lesson),
            ]
        else:
            self.controls = [
                self._lesson_bar(lesson),
                self._scroller(*self._question_panels(lesson, lesson.active)),
                self._lesson_foot(lesson, lesson.active),
            ]

    def _scroller(self, *controls: ft.Control) -> ft.Control:
        """Return the part of the screen between the bar and the buttons.

        Args:
            *controls: What goes in it, top to bottom.

        Returns:
            The scrolling body. The side padding is here rather than on the
            shell so that a bar or a sheet can still run edge to edge.
        """
        return ft.Container(
            content=ft.Column(
                controls=list(controls),
                spacing=GAP,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=ft.Padding.symmetric(horizontal=GAP),
            expand=True,
        )

    # ------------------------------------------------------------------
    # Home
    # ------------------------------------------------------------------

    def _home_state(self) -> HomeState:
        """Return what the home screen should draw itself from.

        Returns:
            The figures, the topics and the topic just practised, plus the
            first thing stopping the app from grading if there is one.
        """
        problems = self._services.config.missing()
        return HomeState(
            summary=self._summary,
            topics=self._topics,
            topic_stats=self._topic_stats,
            problem=problems[0] if problems else None,
            last_topic_id=self._session.last_topic_id,
            last_topic_name=self._session.last_topic_name,
        )

    def _start_from_home(self, topic_id: int | None, topic_name: str) -> None:
        """Start a lesson from a tap on the home screen.

        The home screen's buttons cannot await, so the run is scheduled.

        Args:
            topic_id: The topic to draw from, or ``None`` for a mixed run.
            topic_name: What to call the run on screen.
        """
        self._page.run_task(self.start_lesson, topic_id, topic_name)

    # ------------------------------------------------------------------
    # The lesson
    # ------------------------------------------------------------------

    def _lesson_bar(self, lesson: Lesson) -> ft.Control:
        """Return the progress bar across the top of a lesson.

        Args:
            lesson: The run in progress.

        Returns:
            The way out, how far along the run is, and where in it the user is.
        """
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=22,
                        tooltip="Leave the lesson",
                        on_click=self._on_quit,
                    ),
                    progress_track(lesson.progress),
                    ft.Text(
                        f"{lesson.position}/{lesson.length}",
                        size=12,
                        weight=ft.FontWeight.W_700,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=GAP_SMALL,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(
                left=GAP_TINY, right=GAP, top=GAP_TINY, bottom=GAP_TINY
            ),
        )

    def _question_panels(
        self, lesson: Lesson, active: ActiveExercise
    ) -> list[ft.Control]:
        """Return the question itself.

        Args:
            lesson: The run in progress, for the heading's count.
            active: The exercise in front of the user.

        Returns:
            Where it came from, what to do with it, the picture, and the field.
        """
        return [
            self._meta(lesson, active),
            self._image_card(active),
            self._answer_panel(active),
        ]

    def _meta(self, lesson: Lesson, active: ActiveExercise) -> ft.Control:
        """Return the block above the picture that places the question.

        The heading counts the *lesson*, because the bar directly above it
        does. The book has its own numbering -- the sentence this question is
        in the printed exercise -- and that number is what the user needs to
        find the right line in the picture, so it sits in the pills with the
        unit rather than in the heading, where "Question 6" read as a
        contradiction of the bar's "2/10".

        Args:
            lesson: The run in progress.
            active: The exercise in front of the user.

        Returns:
            The topic, the unit, the sentence, the count and the instruction.
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
                        pill(
                            f"Sentence {active.question.question_id}",
                            icon=ft.Icons.FORMAT_LIST_NUMBERED_ROUNDED,
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=GAP_SMALL,
                    wrap=True,
                    run_spacing=GAP_SMALL,
                ),
                ft.Text(
                    f"Question {lesson.position} of {lesson.length}",
                    size=22,
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

    def _answer_panel(self, active: ActiveExercise) -> ft.Control:
        """Return the answer field, labelled, and locked once it is answered.

        The field is never cleared or hidden by the verdict: reading your own
        words next to the book's is most of what makes a correction land.

        Args:
            active: The exercise in front of the user.

        Returns:
            The label and the field.
        """
        answered = active.is_revealed
        self._answer.read_only = answered
        self._answer.fill_color = ft.Colors.SURFACE_CONTAINER_HIGH if answered else None
        return ft.Column(
            controls=[section_title("Your answer"), self._answer],
            spacing=GAP_SMALL,
            tight=True,
        )

    def _lesson_foot(self, lesson: Lesson, active: ActiveExercise) -> ft.Control:
        """Return whatever is pinned under the question.

        Args:
            lesson: The run in progress.
            active: The exercise in front of the user.

        Returns:
            The verdict sheet once the question has been answered, and the
            buttons that answer it before then.
        """
        if active.is_revealed:
            return self._feedback(lesson, active)
        if self._busy:
            return action_bar(
                ft.ProgressRing(width=18, height=18, stroke_width=2),
                hint("Checking your answer..."),
            )
        return action_bar(
            secondary_action(
                "Reveal",
                icon=ft.Icons.VISIBILITY_ROUNDED,
                tooltip="Show the book's answer without grading",
                on_click=self._on_reveal,
            ),
            primary_action(
                "Check",
                icon=ft.Icons.TASK_ALT_ROUNDED,
                on_click=self._on_check,
            ),
        )

    def _feedback(self, lesson: Lesson, active: ActiveExercise) -> ft.Control:
        """Return the sheet that says how the answer went.

        Args:
            lesson: The run in progress.
            active: The exercise that was just answered.

        Returns:
            The verdict, the book's answer, the rule behind it on request, and
            the one button that moves on.
        """
        evaluation = active.evaluation
        if evaluation is None:
            tint = ft.Colors.TERTIARY_CONTAINER
            on_tint = ft.Colors.ON_TERTIARY_CONTAINER
            icon = ft.Icons.LIGHTBULB_OUTLINE_ROUNDED
        elif evaluation.is_correct:
            tint = ft.Colors.PRIMARY_CONTAINER
            on_tint = ft.Colors.ON_PRIMARY_CONTAINER
            icon = ft.Icons.CHECK_CIRCLE_ROUNDED
        else:
            tint = ft.Colors.ERROR_CONTAINER
            on_tint = ft.Colors.ON_ERROR_CONTAINER
            icon = ft.Icons.CANCEL_ROUNDED

        parts: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Icon(icon, color=on_tint, size=22),
                    ft.Text(
                        self._verdict,
                        size=18,
                        weight=ft.FontWeight.W_700,
                        color=on_tint,
                        expand=True,
                    ),
                ],
                spacing=GAP_SMALL + 2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        ]
        if self._grading_error is not None:
            parts.append(hint(self._grading_error, color=on_tint))
        parts.append(self._answer_note(active))

        return sheet(
            *parts,
            ft.Row(
                controls=[
                    primary_action(
                        "See your result" if lesson.is_complete else "Continue",
                        icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                        on_click=self._on_continue,
                        bgcolor=on_tint,
                        color=tint,
                    )
                ]
            ),
            bgcolor=tint,
        )

    def _answer_note(self, active: ActiveExercise) -> ft.Control:
        """Return the book's answer, on its own surface inside the sheet.

        A neutral card keeps the book's markdown readable whatever colour the
        verdict has painted around it. A correct answer gets the short form
        only: it is confirmation, and confirmation should be quick to dismiss.

        Args:
            active: The exercise that was just answered.

        Returns:
            The card.
        """
        correct = active.evaluation is not None and active.evaluation.is_correct
        answers = active.revealed_answers
        children: list[ft.Control] = []

        if answers:
            children.append(
                ft.Text(
                    short_answer_text(answers),
                    size=16,
                    weight=ft.FontWeight.W_700,
                    selectable=True,
                )
            )
            if not correct:
                # A markdown renderer reads a single newline as a soft wrap,
                # so two answers need a blank line between them.
                children.append(
                    ft.Markdown(
                        full_answer_text(answers, separator="\n\n"),
                        selectable=True,
                    )
                )
        else:
            children.append(
                hint("This question is open-ended, so the book prints no answer.")
            )

        children.extend(self._rule_controls(active))

        return ft.Container(
            content=ft.Column(controls=children, spacing=GAP_SMALL, tight=True),
            padding=GAP_SMALL + 4,
            bgcolor=ft.Colors.SURFACE,
            border_radius=RADIUS_SMALL,
        )

    def _rule_controls(self, active: ActiveExercise) -> list[ft.Control]:
        """Return the rule behind the answer, folded away until it is asked for.

        Args:
            active: The exercise that was just answered.

        Returns:
            Nothing when there is no rule or the user has turned rules off; the
            toggle, and the rule under it when it is open, otherwise.
        """
        rule = active.question.rule
        if not (self._services.config.show_rules and rule):
            return []

        toggle = ft.TextButton(
            content=f"Rule {active.unit_reference}",
            icon=(
                ft.Icons.EXPAND_LESS_ROUNDED
                if self._rule_open
                else ft.Icons.EXPAND_MORE_ROUNDED
            ),
            on_click=self._on_toggle_rule,
        )
        if not self._rule_open:
            return [toggle]

        return [
            toggle,
            ft.Container(
                content=ft.Column(
                    controls=[ft.Markdown(to_markdown(rule), selectable=True)],
                    scroll=ft.ScrollMode.AUTO,
                    tight=True,
                ),
                height=_RULE_HEIGHT,
            ),
        ]

    # ------------------------------------------------------------------
    # The result
    # ------------------------------------------------------------------

    def _result_panels(self, lesson: Lesson) -> list[ft.Control]:
        """Return the screen shown when a lesson is over.

        Args:
            lesson: The run that just finished.

        Returns:
            How it went, in one line and in three figures.
        """
        percent = round(lesson.accuracy * 100)
        return [
            placeholder(
                icon=ft.Icons.EMOJI_EVENTS_ROUNDED,
                title="Lesson complete",
                message=(
                    f"{lesson.correct} of {lesson.answered} correct "
                    f"in {lesson.topic_name}."
                ),
            ),
            ft.Row(
                controls=[
                    stat_tile(
                        f"{percent}%",
                        "this lesson",
                        ft.Icons.TASK_ALT_ROUNDED,
                    ),
                    stat_tile(
                        str(lesson.correct),
                        "correct",
                        ft.Icons.CHECK_CIRCLE_ROUNDED,
                    ),
                    stat_tile(
                        str(lesson.answered - lesson.correct),
                        "to revisit",
                        ft.Icons.REPLAY_ROUNDED,
                        color=ft.Colors.TERTIARY,
                    ),
                ],
                spacing=GAP_SMALL,
            ),
        ]

    def _result_actions(self, lesson: Lesson) -> ft.Control:
        """Return the buttons under a finished lesson.

        Args:
            lesson: The run that just finished.

        Returns:
            The bar: another run of the same, or back to the home screen.
        """
        return action_bar(
            secondary_action(
                "Done",
                icon=ft.Icons.HOME_ROUNDED,
                on_click=self._on_done,
            ),
            primary_action(
                "Practise again",
                icon=ft.Icons.REPLAY_ROUNDED,
                on_click=lambda _: self._page.run_task(
                    self.start_lesson, lesson.topic_id, lesson.topic_name
                ),
            ),
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
                        # Room to drag a magnified crop past the frame's edge,
                        # rather than being clamped with its margin still cut
                        # off.
                        boundary_margin=ft.Margin.all(_ZOOM_PAN_MARGIN),
                    ),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=RADIUS_SMALL,
                    height=_ZOOM_HEIGHT,
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

    def _on_quit(self) -> None:
        """Ask before walking out of a lesson part-way through."""
        self._page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Leave this lesson?"),
                content=ft.Text(
                    "The questions you have already answered are kept, but the "
                    "rest of the run is dropped."
                ),
                actions=[
                    ft.TextButton("Stay", on_click=lambda _: self._page.pop_dialog()),
                    ft.FilledButton(content="Leave", on_click=self._on_leave),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                shape=ft.RoundedRectangleBorder(radius=RADIUS),
            )
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def _on_leave(self) -> None:
        """Leave the lesson, once the user has confirmed it."""
        self._page.pop_dialog()
        await self._end_lesson()

    async def _on_done(self) -> None:
        """Close a finished lesson."""
        await self._end_lesson()

    def _on_toggle_rule(self) -> None:
        """Fold the rule open or shut."""
        self._rule_open = not self._rule_open
        self.render()
        push(self)

    async def _on_reveal(self) -> None:
        """Give up on the question and show the book's answer."""
        lesson = self._session.lesson
        if lesson is None or lesson.active is None:  # pragma: no cover - guarded
            return
        lesson.active.ungraded = True
        # Revealing spends the question but earns nothing: a run of reveals
        # must not read back as a perfect lesson.
        lesson.record(correct=False)
        self._verdict = _REVEALED_HEADLINE
        self.render()
        push(self)

    async def _on_check(self) -> None:
        """Grade what the user typed."""
        lesson = self._session.lesson
        if lesson is None or lesson.active is None:  # pragma: no cover - guarded
            return
        if self._busy:  # pragma: no cover - the button is gone while busy
            return
        active = lesson.active

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
            self._verdict = _REVEALED_HEADLINE
            # Some provider messages end in a full stop and some do not, so
            # the sentence is closed here rather than trusting either.
            self._grading_error = f"{_GRADING_FAILED} {str(exc).rstrip('.')}."
            lesson.record(correct=False)
        else:
            active.evaluation = evaluation
            self._verdict = verdict_phrase(evaluation.is_correct)
            lesson.record(correct=evaluation.is_correct)
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

    async def _on_continue(self) -> None:
        """Move past the verdict: on to the next question, or to the result."""
        lesson = self._session.lesson
        if lesson is None:  # pragma: no cover - the sheet is not on screen
            return

        if lesson.is_complete:
            lesson.active = None
            await self._reload_stats()
        else:
            drawn = await self._draw(lesson.topic_id, lesson.topic_name)
            if drawn is None:
                return
            lesson.active = drawn
            self._answer.value = ""
            self._rule_open = False
            self._grading_error = None

        self.render()
        push(self)

    # ------------------------------------------------------------------
    # Running a lesson
    # ------------------------------------------------------------------

    async def start_lesson(self, topic_id: int | None, topic_name: str) -> None:
        """Draw the first question of a run and hand the screen over to it.

        The question is drawn before the lesson exists, so a topic with nothing
        in it leaves the user on the home screen with a message rather than
        inside an empty lesson they have to back out of.

        Args:
            topic_id: The topic to draw from, or ``None`` for a mixed run.
            topic_name: What to call the run on screen.
        """
        drawn = await self._draw(topic_id, topic_name)
        if drawn is None:
            return

        self._answer.value = ""
        self._rule_open = False
        self._grading_error = None
        lesson = self._session.begin(topic_id, topic_name)
        lesson.active = drawn

        self._announce()
        self.render()
        push(self)

    async def _draw(
        self, topic_id: int | None, topic_name: str
    ) -> ActiveExercise | None:
        """Draw one question, with everything needed to grade and show it.

        Args:
            topic_id: The topic to draw from, or ``None`` for any.
            topic_name: What to call it on screen.

        Returns:
            The question, or ``None`` when there was nothing to draw — in which
            case the user has already been told why.
        """
        try:
            drawn = await self._services.content.draw_question(topic_id)
        except ContentError as exc:
            show_snack(self._page, str(exc), error=True)
            return None

        if drawn is None:
            show_snack(self._page, _NO_EXERCISES)
            return None

        exercise, question, image = drawn
        try:
            answers = await self._services.content.list_answers(question.id)
        except ContentError as exc:  # pragma: no cover - the draw already read it
            show_snack(self._page, str(exc), error=True)
            return None

        return ActiveExercise(
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

    async def _end_lesson(self) -> None:
        """Put the lesson down and go back to the home screen."""
        self._session.end()
        await self._reload_stats()
        self._announce()
        self.render()
        push(self)

    def _announce(self) -> None:
        """Tell the shell whether a lesson has the screen to itself."""
        if self._on_lesson_change is not None:
            self._on_lesson_change(self._session.lesson is not None)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def load(self) -> None:
        """Load what the home screen shows: the topics, and today's progress.

        The topics are read once — they ship with the app and cannot change —
        while the figures are read every time, so the card is current whenever
        the tab comes back into view.
        """
        if not self._topics:
            try:
                self._topics = tuple(await self._services.content.list_topics())
            except ContentError as exc:
                show_snack(self._page, str(exc), error=True)
        await self._reload_stats()
        self.render()
        push(self)

    async def _reload_stats(self) -> None:
        """Re-read the progress the home screen reports."""
        self._summary = await self._services.stats.summary()
        self._topic_stats = {topic.name: topic for topic in self._summary.topics}

    def refresh(self) -> None:
        """Re-render after a settings change, which may hide the setup notice."""
        self.render()
        push(self)
