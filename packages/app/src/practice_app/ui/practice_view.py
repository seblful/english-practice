"""The practice screen: a lesson, one question at a time.

The shape here is a studying app's rather than a conversation's. A lesson is a
fixed run of questions: a bar across the top says how far along it is, the
question owns the middle of the screen, the action sits under the thumb, and
the verdict arrives as a sheet over the bottom.

That last part is the point. Nothing accumulates: the question the user just
answered stays exactly where it was, with their own words still in the field
beside the book's, instead of scrolling away above a growing transcript of
panels. What is on screen is the question being worked on, and that is all.

Nothing here opens a dialog. A lesson is a full-screen task on a phone, and a
box floating over the middle of one -- to say what a unit covers, to magnify
the picture, to ask whether the user really means to leave -- reads as an
interruption from somewhere else. So every one of those is part of the screen
instead: what the unit covers unfolds from the unit's own chip, the picture
magnifies into the whole screen, and leaving is asked in the same sheet the
verdict arrives in.
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
from practice_core.reveal import Reveal

from practice_app.services import Services
from practice_app.session import ActiveExercise, Lesson, PracticeSession
from practice_app.stats import Attempt, StatsSummary, TopicStat
from practice_app.ui import motion
from practice_app.ui.components import (
    SCROLL,
    STRETCH,
    action_bar,
    banner,
    hint,
    link_action,
    pill,
    placeholder,
    primary_action,
    progress_track,
    secondary_action,
    section_title,
    sheet,
    show_snack,
    stat_tile,
    text_field,
)
from practice_app.ui.home_view import HomeState, HomeView
from practice_app.ui.page import DialogPage
from practice_app.ui.screen import Screen
from practice_app.ui.theme import (
    CORRECT,
    GAP,
    GAP_SMALL,
    GAP_TINY,
    ON_CORRECT,
    RADIUS,
    RADIUS_SMALL,
)

if TYPE_CHECKING:  # pragma: no cover - the topics are only ever annotated here
    from practice_core.models import Topic

__all__ = ["PracticeScreen"]

_REVEALED_HEADLINE = "Here is the answer"

# The slots every state fills -- see :meth:`PracticeScreen.render`.
_BAR_REGION = "practice.bar"
_BODY_REGION = "practice.body"

# Outside the region, so the inset does not fade with the bar's contents.
_BAR_FRAME_KEY = "practice.bar.frame"

# The parts of a question that come and go on their own, each one a slot.
_IMAGE_REGION = "practice.body.image"
_UNIT_REGION = "practice.body.unit"
_RULE_REGION = "practice.foot.rule"

# Keyed because the rule folds open inside it, and a slot needs keys above.
_NOTE_KEY = "practice.foot.note"

# Kept across questions, so the client updates the bar it already has.
_PROGRESS_KEY = "practice.progress"

# Keyed so a rebuild updates the field the user is already typing into.
_ANSWER_KEY = "practice.answer"

_NO_EXERCISES = "No exercises found for this topic. Try another one."
_EMPTY_ANSWER = "Type your answer first."
_GRADING_FAILED = "Could not grade that. Here is the book's answer."

# Capped, so the sheet cannot push the question it explains off screen.
_RULE_HEIGHT = 160

# Without it a magnified crop is clamped with its own margin still cut off.
_ZOOM_PAN_MARGIN = 80

# Three lines for a sentence-long answer, six before the field scrolls.
_ANSWER_MIN_LINES = 3
_ANSWER_MAX_LINES = 6


class PracticeScreen(Screen):
    """A lesson: a run of questions, one on screen at a time."""

    tab_title = "Practice"
    tab_label = "Practice"
    tab_icon = ft.Icons.SCHOOL_ROUNDED
    # The progress bar and the verdict sheet run edge to edge.
    inset = False

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
        # Drawn once per verdict, so folding the rule open does not re-roll it.
        self._verdict = ""
        # In the sheet, not a snack bar: a snack covers the button that moves on.
        self._grading_error: str | None = None
        self._rule_open = False
        # Shuts with every new question: it belongs to the question, not the run.
        self._unit_open = False
        # Two panes the lesson puts over itself, part of the screen not dialogs.
        self._zoom_open = False
        self._leaving = False

        # Rebuilt rather than reconfigured -- see :meth:`_answer_field`.
        self._answer = self._answer_field(answered=False, typed="")

        super().__init__(spacing=0, expand=True, horizontal_alignment=STRETCH)
        self.render()

    # --- Rendering ---

    def render(self) -> None:
        """Rebuild the screen from the current state.

        Which state is showing is read off the session and two flags: no
        lesson is the home screen, a lesson whose question has been put down
        is the result, a lesson with a question is the lesson itself -- and
        the magnified picture, while it is open, is the whole screen.

        Whichever it is, it is assembled out of the same three slots, and each
        one is named the same on every repaint. That is what makes the change
        between two of these states a change the client can animate rather
        than a new screen it has to mount: the body cross-fades from one state
        to the next, the bar cross-fades between the lesson's and the
        picture's, and the foot tweens its surface underneath whichever of the
        four things it is holding.
        """
        lesson = self._session.lesson
        if lesson is None:
            self.controls = [
                self._body(
                    "home", self._scroller(*self._home.build(self._home_state()))
                )
            ]
            return

        active = lesson.active
        if active is None:
            self.controls = [
                self._body("result", self._scroller(*self._result_panels(lesson))),
                self._result_actions(lesson),
            ]
            return

        image = active.image
        if self._zoom_open and image is not None:
            self.controls = self._zoom_pane(active, image)
            return

        self.controls = [
            self._lesson_bar(lesson),
            self._body("lesson", self._scroller(*self._question_panels(active))),
            self._lesson_foot(lesson, active),
        ]

    def _body(self, state: str, content: ft.Control) -> ft.Control:
        """Return the screen's main slot, showing one of its states.

        Args:
            state: Which state ``content`` is. The home screen, a question, a
                finished lesson and the magnified picture are four different
                screens as far as the user is concerned, so each one arriving
                is worth the full :data:`~practice_app.ui.motion.Swap.SCREEN`.
            content: What to show.

        Returns:
            The slot.
        """
        return motion.swap(
            region=_BODY_REGION,
            state=state,
            content=content,
            pace=motion.Swap.SCREEN,
            expand=True,
        )

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
                scroll=SCROLL,
                expand=True,
                horizontal_alignment=STRETCH,
            ),
            padding=ft.Padding.symmetric(horizontal=GAP),
            expand=True,
        )

    # --- Home ---

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

    # --- The lesson ---

    def _bar(self, state: str, content: ft.Control) -> ft.Control:
        """Return the strip across the top of the screen, in one of its states.

        Args:
            state: Which bar this is -- the lesson's, or the picture's.
            content: What goes in it.

        Returns:
            The slot. The lesson's bar and the magnified picture's are the same
            slot on purpose: the way out sits in the same place in both, so
            crossing between them should move the label and not the bar.
        """
        return ft.Container(
            key=_BAR_FRAME_KEY,
            content=motion.swap(region=_BAR_REGION, state=state, content=content),
            padding=ft.Padding.only(
                left=GAP_TINY, right=GAP, top=GAP_TINY, bottom=GAP_TINY
            ),
        )

    def _lesson_bar(self, lesson: Lesson) -> ft.Control:
        """Return the progress bar across the top of a lesson.

        Args:
            lesson: The run in progress.

        Returns:
            The way out, how far along the run is, and where in it the user is.
        """
        return self._bar(
            "lesson",
            ft.Row(
                controls=[
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_size=22,
                        tooltip="Leave the lesson",
                        on_click=lambda _: self.request_leave(),
                    ),
                    motion.keyed(progress_track(lesson.progress), _PROGRESS_KEY),
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
        )

    def _question_panels(self, active: ActiveExercise) -> list[ft.Control]:
        """Return the question itself.

        Args:
            active: The exercise in front of the user.

        Returns:
            Where it came from, what to do with it, the picture, and the field.
        """
        return [
            motion.keyed(self._meta(active), f"{_BODY_REGION}.meta"),
            motion.swap(
                region=_IMAGE_REGION,
                # Different shapes: a shared key patches instead of replacing.
                state="picture" if active.image is not None else "none",
                content=self._image_card(active),
                resizes=True,
            ),
            self._answer_panel(active),
        ]

    def _meta(self, active: ActiveExercise) -> ft.Control:
        """Return the block above the picture that places the question.

        The heading is the book's own numbering -- which sentence of the
        printed exercise this is -- because that is the number the user reads
        the picture with. How far along the lesson is belongs to the bar
        directly above it, and saying it again here, in a different counting,
        is what made "Question 6" read as a contradiction of "2/10".

        Args:
            active: The exercise in front of the user.

        Returns:
            The topic, the unit, what the unit covers while it is unfolded,
            the sentence, and the instruction.
        """
        unit = active.exercise.unit
        children: list[ft.Control] = [
            ft.Row(
                controls=[
                    pill(active.topic_name, icon=ft.Icons.CATEGORY_ROUNDED),
                    pill(
                        f"Unit {unit.unit_number}",
                        icon=ft.Icons.MENU_BOOK_ROUNDED,
                        trailing=(
                            ft.Icons.EXPAND_LESS_ROUNDED
                            if self._unit_open
                            else ft.Icons.EXPAND_MORE_ROUNDED
                        ),
                        on_click=lambda _: self._toggle_unit(),
                        tooltip="What this unit covers",
                    ),
                ],
                spacing=GAP_SMALL,
                wrap=True,
                run_spacing=GAP_SMALL,
            )
        ]
        # Unfolded from the chip it belongs to; shut, it is a box of no height.
        children.append(
            motion.swap(
                region=_UNIT_REGION,
                state="open" if self._unit_open else "shut",
                content=(
                    ft.Text(
                        unit.title,
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                    if self._unit_open
                    else ft.Container(height=0)
                ),
                pace=motion.Swap.DETAIL,
                resizes=True,
            )
        )
        children.extend(
            [
                ft.Text(
                    f"Sentence {active.question.question_id}",
                    size=22,
                    weight=ft.FontWeight.W_700,
                ),
                hint(
                    "Answer in your own words - the grammar is what counts."
                    if active.question.is_open_ended
                    else "Type the missing words, or the whole sentence."
                ),
            ]
        )
        return ft.Column(
            controls=children,
            spacing=GAP_SMALL,
            tight=True,
            horizontal_alignment=STRETCH,
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
            content=ft.Column(
                controls=[
                    # A radius would clip the exercise number out of a corner.
                    ft.Image(
                        src=active.image,
                        fit=ft.BoxFit.FIT_WIDTH,
                        gapless_playback=True,
                    ),
                    # Under the crop: a badge on top would cover a printed line.
                    ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.ZOOM_IN_ROUNDED,
                                size=14,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Text(
                                "Tap to zoom",
                                size=11,
                                weight=ft.FontWeight.W_500,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=GAP_TINY,
                        alignment=ft.MainAxisAlignment.END,
                        tight=True,
                    ),
                ],
                spacing=GAP_TINY,
                tight=True,
                horizontal_alignment=STRETCH,
            ),
            padding=GAP_SMALL,
            bgcolor=ft.Colors.WHITE,
            border_radius=RADIUS,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=lambda _: self._open_zoom(),
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
        self._answer = self._answer_field(
            answered=active.is_revealed, typed=self._answer.value or ""
        )
        return motion.keyed(
            ft.Column(
                controls=[section_title("Your answer"), self._answer],
                spacing=GAP_SMALL,
                tight=True,
                horizontal_alignment=STRETCH,
            ),
            f"{_BODY_REGION}.answer",
        )

    def _reset_answer(self) -> None:
        """Start the next question with an empty field.

        This used to assign to the outgoing field's ``value``, which is a
        mutation of a control that may by then be frozen -- Flet freezes the
        controls it mounts during a keyed pass. Replacing the reference
        touches nothing on screen: the next render builds the field from it.
        """
        self._answer = self._answer_field(answered=False, typed="")

    def _answer_field(self, *, answered: bool, typed: str) -> ft.TextField:
        """Return the answer field in the state this question leaves it.

        A field is built rather than reconfigured, and the reason is Flet's
        rather than this screen's. Once any part of a screen is keyed, Flet
        reconciles the rest by key too -- and it marks every control it *adds*
        during such a pass frozen, which makes further assignment to that
        control raise. A stable field reconfigured on each render was therefore
        exactly the thing that could no longer be reconfigured: the first
        cross-fade into a lesson froze it. Rebuilding it costs nothing, and it
        leaves :meth:`render` free of side effects on anything but this
        reference.

        The key is what carries the client's own state across the rebuild, so
        the text is not retyped, the cursor does not jump, and Material has a
        previous fill colour to animate away from when the answer locks.

        Args:
            answered: Whether the question has been put down, which locks the
                field and greys it.
            typed: What is already in it. Read off the outgoing field, because
                that is the one the client has been sending keystrokes to.

        Returns:
            The field.
        """
        return motion.keyed(
            text_field(
                hint_text="Type your answer",
                value=typed,
                multiline=True,
                shift_enter=True,
                min_lines=_ANSWER_MIN_LINES,
                max_lines=_ANSWER_MAX_LINES,
                text_size=16,
                autocorrect=False,
                capitalization=ft.TextCapitalization.NONE,
                read_only=answered,
                fill_color=ft.Colors.SURFACE_CONTAINER_HIGH if answered else None,
                on_submit=self._on_check,
            ),
            _ANSWER_KEY,
        )

    def _lesson_foot(self, lesson: Lesson, active: ActiveExercise) -> ft.Control:
        """Return whatever is pinned under the question.

        Args:
            lesson: The run in progress.
            active: The exercise in front of the user.

        Returns:
            The leave question while it is being asked, the verdict sheet once
            the question has been answered, and the buttons that answer it
            before then.
        """
        if self._leaving:
            return self._leave_sheet()
        if active.is_revealed:
            return self._feedback(lesson, active)
        if self._busy:
            return action_bar(
                ft.ProgressRing(width=18, height=18, stroke_width=2),
                hint("Checking your answer..."),
                state="busy",
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
            state="actions",
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
            verdict_state = "verdict:revealed"
        elif evaluation.is_correct:
            tint = CORRECT
            on_tint = ON_CORRECT
            icon = ft.Icons.CHECK_CIRCLE_ROUNDED
            verdict_state = "verdict:right"
        else:
            tint = ft.Colors.ERROR_CONTAINER
            on_tint = ft.Colors.ON_ERROR_CONTAINER
            icon = ft.Icons.CANCEL_ROUNDED
            verdict_state = "verdict:wrong"

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
            # Three things to be told, so three states cross-fading over the tint.
            state=verdict_state,
        )

    def _answer_note(self, active: ActiveExercise) -> ft.Control:
        """Return the book's answer, on its own surface inside the sheet.

        A neutral card keeps the book's markdown readable whatever colour the
        verdict has painted around it. *What* goes in it -- which answers, and
        whether the book's whole sentence adds anything to the short form --
        is :func:`practice_core.reveal.reveal_for`'s decision, shared with the
        bot so that one graded answer cannot read two ways.

        Args:
            active: The exercise that was just answered.

        Returns:
            The card.
        """
        reveal = active.reveal(show_rule=self._services.config.show_rules)
        children: list[ft.Control] = []

        if reveal.has_answer:
            children.append(
                ft.Text(
                    short_answer_text(reveal.answers),
                    size=17,
                    weight=ft.FontWeight.W_700,
                    selectable=True,
                )
            )
            if reveal.show_full_answer:
                children.append(
                    ft.Markdown(
                        # One newline is a soft wrap to a markdown renderer.
                        full_answer_text(reveal.answers, separator="\n\n"),
                        selectable=True,
                    )
                )
        elif active.question.is_open_ended:
            children.append(
                hint("This question is open-ended, so the book prints no answer.")
            )
        else:
            # A closed question with no answers is a gap in the import, not an offer.
            children.append(hint("The book records no answer for this question."))

        children.extend(self._rule_controls(reveal))

        return motion.keyed(
            ft.Container(
                content=ft.Column(
                    controls=children,
                    spacing=GAP_SMALL,
                    tight=True,
                    horizontal_alignment=STRETCH,
                ),
                padding=GAP_SMALL + 4,
                bgcolor=ft.Colors.SURFACE,
                border_radius=RADIUS_SMALL,
            ),
            _NOTE_KEY,
        )

    def _rule_controls(self, reveal: Reveal) -> list[ft.Control]:
        """Return the rule behind the answer, folded away until it is asked for.

        Args:
            reveal: What was decided for the question just answered.

        Returns:
            Nothing when there is no rule to show; the toggle, and the rule
            under it when it is open, otherwise.
        """
        rule = reveal.rule
        if rule is None:
            return []

        toggle = ft.Row(
            controls=[
                link_action(
                    f"Rule {reveal.unit_reference}",
                    icon=(
                        ft.Icons.EXPAND_LESS_ROUNDED
                        if self._rule_open
                        else ft.Icons.EXPAND_MORE_ROUNDED
                    ),
                    on_click=self._on_toggle_rule,
                )
            ],
            tight=True,
        )
        return [
            toggle,
            motion.swap(
                region=_RULE_REGION,
                state="open" if self._rule_open else "shut",
                content=(
                    ft.Container(
                        content=ft.Column(
                            controls=[ft.Markdown(to_markdown(rule), selectable=True)],
                            scroll=SCROLL,
                            tight=True,
                        ),
                        height=_RULE_HEIGHT,
                    )
                    if self._rule_open
                    else ft.Container(height=0)
                ),
                pace=motion.Swap.DETAIL,
                resizes=True,
            ),
        ]

    # --- The result ---

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
            state="result",
        )

    # --- The picture, magnified ---

    def _zoom_pane(self, active: ActiveExercise, image: bytes) -> list[ft.Control]:
        """Return the whole screen given over to the exercise image.

        A phone has one screen and the crop wants all of it, so this replaces
        the lesson rather than floating over it - and the way back is the same
        bar the lesson's own way out sits in.

        Args:
            active: The exercise in front of the user.
            image: Its picture, which the caller has already found.

        Returns:
            The bar, and the picture under it.
        """
        return [
            self._bar(
                "zoom",
                ft.Row(
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK_ROUNDED,
                            icon_size=22,
                            tooltip="Back to the question",
                            on_click=lambda _: self._close_zoom(),
                        ),
                        ft.Text(
                            f"Unit {active.exercise.unit.unit_number}",
                            size=14,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                        ),
                        hint("Pinch to zoom"),
                    ],
                    spacing=GAP_SMALL,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            self._body(
                "zoom",
                ft.Container(
                    # The viewer takes the frame: loose constraints drew nothing.
                    content=ft.InteractiveViewer(
                        content=ft.Container(
                            # The sheet hugs the picture, not the frame.
                            content=ft.Container(
                                content=ft.Image(src=image, fit=ft.BoxFit.FIT_WIDTH),
                                padding=GAP_SMALL,
                                bgcolor=ft.Colors.WHITE,
                                border_radius=RADIUS,
                            ),
                            alignment=ft.Alignment.CENTER,
                        ),
                        min_scale=1,
                        max_scale=6,
                        boundary_margin=ft.Margin.all(_ZOOM_PAN_MARGIN),
                        expand=True,
                    ),
                    margin=ft.Margin.only(left=GAP, right=GAP, bottom=GAP),
                    expand=True,
                ),
            ),
        ]

    # --- Leaving a lesson ---

    def _leave_sheet(self) -> ft.Control:
        """Return the question asked on the way out of a lesson.

        It is the same sheet the verdict arrives in, for the same reason: the
        question and the answer the user is part-way through stay on screen
        while they decide, instead of being greyed out behind a box.

        Returns:
            The sheet: what leaving costs, and the two ways to answer.
        """
        on_tint = ft.Colors.ON_SECONDARY_CONTAINER
        return sheet(
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.LOGOUT_ROUNDED, color=on_tint, size=22),
                    ft.Text(
                        "Leave this lesson?",
                        size=18,
                        weight=ft.FontWeight.W_700,
                        color=on_tint,
                        expand=True,
                    ),
                ],
                spacing=GAP_SMALL + 2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            hint(
                "The questions you have already answered are kept, but the "
                "rest of the run is dropped.",
                color=on_tint,
            ),
            ft.Row(
                controls=[
                    secondary_action(
                        "Stay",
                        icon=ft.Icons.ARROW_BACK_ROUNDED,
                        on_click=lambda _: self._stay(),
                    ),
                    primary_action(
                        "Leave",
                        icon=ft.Icons.LOGOUT_ROUNDED,
                        on_click=self._on_leave,
                        bgcolor=on_tint,
                        color=ft.Colors.SECONDARY_CONTAINER,
                    ),
                ],
                spacing=GAP_SMALL,
            ),
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            state="leaving",
        )

    # --- What the back gesture asks for ---

    def handle_back(self) -> bool:
        """Take the system Back gesture, if this screen has a use for it.

        Back is the same gesture as the lesson's cross, and letting it close
        the app mid-lesson was the app's rudest bug: ten questions in, and the
        run is gone with nothing asked.

        Returns:
            Whether the gesture was used. ``False`` means this screen has
            nothing open and the shell may do what it likes with it.
        """
        if self._zoom_open:
            self._close_zoom()
            return True
        if self._leaving:
            self._stay()
            return True
        lesson = self._session.lesson
        if lesson is None:
            return False
        if lesson.active is None:
            # The result is on screen; there is nothing left to lose.
            self._page.run_task(self._end_lesson)
            return True
        self.request_leave()
        return True

    def request_leave(self) -> None:
        """Ask whether to leave the lesson, from the cross or from Back."""
        if self._session.lesson is None:  # pragma: no cover - both guard it
            return
        self._leaving = True
        self.repaint()

    def _stay(self) -> None:
        """Put the leave question away and carry on with the question."""
        self._leaving = False
        self.repaint()

    def _open_zoom(self) -> None:
        """Give the screen over to the exercise picture."""
        self._zoom_open = True
        self.repaint()

    def _close_zoom(self) -> None:
        """Go back to the question from the magnified picture."""
        self._zoom_open = False
        self.repaint()

    # --- Events ---

    async def _on_leave(self) -> None:
        """Leave the lesson, once the user has confirmed it."""
        await self._end_lesson()

    async def _on_done(self) -> None:
        """Close a finished lesson."""
        await self._end_lesson()

    def _toggle_unit(self) -> None:
        """Fold what the unit covers open or shut, from a tap on its chip."""
        self._unit_open = not self._unit_open
        self.repaint()

    def _on_toggle_rule(self) -> None:
        """Fold the rule open or shut."""
        self._rule_open = not self._rule_open
        self.repaint()

    async def _on_reveal(self) -> None:
        """Give up on the question and show the book's answer."""
        lesson = self._session.lesson
        if lesson is None or lesson.active is None:  # pragma: no cover - guarded
            return
        # The lesson keeps the rule that revealing earns nothing.
        lesson.reveal_answer()
        self._verdict = _REVEALED_HEADLINE
        self.repaint()

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
        self.repaint()

        try:
            evaluation = await self._services.grader.grade(
                question=active.question,
                user_input=typed,
                answers=active.answers,
                topic_name=active.topic_name,
                image=active.image,
            )
        except PracticeError as exc:
            lesson.grading_failed()
            self._verdict = _REVEALED_HEADLINE
            self._grading_error = f"{_GRADING_FAILED} {exc}"
        else:
            lesson.check(evaluation)
            self._verdict = verdict_phrase(evaluation.is_correct)
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
            self.repaint()

    async def _on_continue(self) -> None:
        """Move past the verdict: on to the next question, or to the result."""
        lesson = self._session.lesson
        if lesson is None:  # pragma: no cover - the sheet is not on screen
            return

        if lesson.is_complete:
            lesson.finish()
            await self._reload_stats()
        else:
            drawn = await self._draw(lesson.topic_id, lesson.topic_name)
            if drawn is None:
                return
            lesson.advance(drawn)
            self._reset_answer()
            self._rule_open = False
            self._unit_open = False
            self._grading_error = None

        self.repaint()

    # --- Running a lesson ---

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

        self._reset_answer()
        self._rule_open = False
        self._unit_open = False
        self._grading_error = None
        self._close_panes()
        lesson = self._session.begin(topic_id, topic_name)
        lesson.advance(drawn)

        self._announce()
        self.repaint()

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
            active = await self._services.content.draw(topic_id, topic_name=topic_name)
        except ContentError as exc:
            show_snack(self._page, str(exc), error=True)
            return None

        if active is None:
            show_snack(self._page, _NO_EXERCISES)
            return None

        return active

    def _close_panes(self) -> None:
        """Put away anything the lesson had open over itself.

        Both flags outlive the lesson they belong to otherwise, and a leave
        question left standing greets the *next* lesson with its own way out
        already on screen.
        """
        self._leaving = False
        self._zoom_open = False

    async def _end_lesson(self) -> None:
        """Put the lesson down and go back to the home screen."""
        self._session.end()
        self._close_panes()
        await self._reload_stats()
        self._announce()
        self.repaint()

    def _announce(self) -> None:
        """Tell the shell whether a lesson has the screen to itself."""
        if self._on_lesson_change is not None:
            self._on_lesson_change(self._session.lesson is not None)

    # --- Loading ---

    async def reload(self) -> None:
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
        self.repaint()

    async def _reload_stats(self) -> None:
        """Re-read the progress the home screen reports."""
        self._summary = await self._services.stats.summary()
        self._topic_stats = {topic.name: topic for topic in self._summary.topics}
