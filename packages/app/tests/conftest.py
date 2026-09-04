"""Shared fixtures for the app tests."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from practice_core.content import ContentLibrary
from practice_core.models import Question, QuestionAnswer
from practice_core.schema import create_content_schema

from practice_app.config import AppConfig, ConfigStore, ProviderConfig
from practice_app.providers import ModelInfo, Provider, ThinkingLevel
from practice_app.services import Services
from practice_app.stats import StatsStore

SEED = """
INSERT INTO units (id, unit_number, title)
VALUES (1, 1, 'Present Continuous'), (2, 2, 'Past Simple');

INSERT INTO topics (id, name) VALUES (1, 'Present Tenses'), (2, 'Past Tenses');

INSERT INTO unit_topics (unit_id, topic_id) VALUES (1, 1), (2, 2);

INSERT INTO exercises (id, exercise_id, unit_id, exercise_number)
VALUES (1, '1.1', 1, 1), (2, '2.1', 2, 1);

INSERT INTO exercise_images (exercise_id, image_data) VALUES (1, X'89504E470D0A1A0A');

INSERT INTO questions
    (id, exercise_id, question_id, is_open_ended, section_letter, rule, display_order)
VALUES
    (1, 1, '2', 0, 'A', 'Use present continuous', 0),
    (2, 2, '1', 1, 'B', NULL, 0);

INSERT INTO question_answers (question_id, short_answer, full_answer)
VALUES (1, 'is doing', 'He **is doing** it.'),
       (1, "'s doing", "He **'s doing** it.");
"""

PNG_BYTES = b"\x89PNG\r\n\x1a\n"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPfake"


# --- A page a screen can be built against ---


@dataclass
class FakeView:
    """The root view, as the shell uses it: it may refuse to be popped."""

    can_pop: bool = True
    on_confirm_pop: Any = None
    confirmed: list[bool] = field(default_factory=list)

    async def confirm_pop(self, should_pop: bool) -> None:
        """Record the shell's answer to a pending Back gesture."""
        self.confirmed.append(should_pop)


@dataclass
class FakePage:
    """The part of ``ft.Page`` the screens actually touch."""

    dialogs: list[Any] = field(default_factory=list)
    popped: int = 0
    launched: list[str] = field(default_factory=list)
    tasks: list[tuple[Any, tuple[Any, ...]]] = field(default_factory=list)

    updates: int = 0
    title: str | None = None
    theme: Any = None
    dark_theme: Any = None
    theme_mode: Any = None
    padding: Any = None
    appbar: Any = None
    navigation_bar: Any = None
    on_disconnect: Any = None
    controls: list[Any] = field(default_factory=list)
    views: list[FakeView] = field(default_factory=lambda: [FakeView()])

    def show_dialog(self, dialog: Any) -> None:
        """Record a dialog or snack bar the screen opened."""
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        """Record that the screen closed the top dialog."""
        self.popped += 1

    async def launch_url(self, url: str) -> None:
        """Record an external link the screen opened."""
        self.launched.append(url)

    def run_task(self, handler: Any, *args: Any) -> None:
        """Record a coroutine the screen scheduled instead of awaiting."""
        self.tasks.append((handler, args))

    def add(self, *controls: Any) -> None:
        """Record controls added to the page."""
        self.controls.extend(controls)

    def update(self) -> None:
        """Count a page-level push, which is how the shell sends its chrome."""
        self.updates += 1

    # --- Helpers for the tests themselves ---

    @property
    def root_view(self) -> FakeView:
        """Return the view the shell wired its Back handler to."""
        return self.views[0]

    @property
    def last_dialog(self) -> Any:
        """Return the most recently opened dialog."""
        assert self.dialogs, "no dialog was opened"
        return self.dialogs[-1]

    def snack_texts(self) -> list[str]:
        """Return the text of every snack bar shown."""
        return [
            dialog.content.value
            for dialog in self.dialogs
            if type(dialog).__name__ == "SnackBar"
        ]

    async def drain(self) -> None:
        """Run every coroutine the screen scheduled, oldest first."""
        pending, self.tasks = self.tasks, []
        for handler, args in pending:
            await handler(*args)


@pytest.fixture
def page() -> FakePage:
    """A page stand-in, empty for each test."""
    return FakePage()


# --- Content and progress ---


@pytest.fixture
def content_db(tmp_path: Path) -> Path:
    """Build a small content database from the shared schema."""
    path = tmp_path / "content.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        create_content_schema(conn)
        conn.executescript(SEED)
    return path


@pytest.fixture
def content(content_db: Path) -> ContentLibrary:
    """A read-only library over the seeded content, as the app opens it."""
    return ContentLibrary(content_db, read_only=True)


@pytest.fixture
def stats(tmp_path: Path) -> StatsStore:
    """A progress store in a scratch directory."""
    return StatsStore(tmp_path / "progress.db")


@pytest.fixture
def frozen_clock() -> Callable[[], datetime]:
    """A clock stuck at a fixed instant, for the streak arithmetic."""
    return lambda: datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


# --- Settings ---


@pytest.fixture
def config_store(tmp_path: Path) -> ConfigStore:
    """A settings store in a scratch directory."""
    return ConfigStore(tmp_path / "settings.json")


@pytest.fixture
def config() -> AppConfig:
    """Settings that are ready to grade, on OpenRouter."""
    return AppConfig(
        provider=Provider.OPENROUTER,
        providers={
            provider: ProviderConfig(
                api_key="test-key",
                model="vendor/model",
                thinking=ThinkingLevel.OFF,
            )
            for provider in Provider
        },
    )


# --- Provider calls ---


def json_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """Return a transport that answers with whatever ``handler`` decides."""
    return httpx.MockTransport(handler)


def reply_transport(
    text: str, *, status: int = 200, record: list[httpx.Request] | None = None
) -> httpx.MockTransport:
    """Return a transport that answers every request with one chat reply."""

    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record.append(request)
        return httpx.Response(
            status, json={"choices": [{"message": {"content": text}}]}
        )

    return httpx.MockTransport(handler)


@pytest.fixture
def services(
    config_store: ConfigStore,
    content: ContentLibrary,
    stats: StatsStore,
    config: AppConfig,
) -> Services:
    """Services whose provider calls succeed with a correct verdict."""
    return Services(
        config_store=config_store,
        content=content,
        stats=stats,
        config=config,
        transport=reply_transport('{"is_correct": true, "answer_idx": [0]}'),
    )


@pytest.fixture
def question() -> Question:
    """A closed question with a rule attached."""
    return Question(
        id=1,
        question_id="2",
        is_open_ended=False,
        section_letter="A",
        rule="Use present continuous",
    )


@pytest.fixture
def answers() -> list[QuestionAnswer]:
    """Two accepted answers."""
    return [
        QuestionAnswer(short_answer="is doing", full_answer="He **is doing** it."),
        QuestionAnswer(short_answer="'s doing", full_answer="He **'s doing** it."),
    ]


@pytest.fixture
def catalogue() -> list[ModelInfo]:
    """A small model catalogue covering every badge the picker shows."""
    return [
        ModelInfo(
            id="vendor/model",
            name="Vendor Model",
            description="A vision model that reasons.",
            context_length=1_048_576,
            supports_thinking=True,
            supports_images=True,
            supports_json=True,
            prompt_price=0.0000005,
            completion_price=0.0000015,
        ),
        ModelInfo(
            id="vendor/text-only",
            name="Vendor Text",
            description="Text in, text out.",
            context_length=8_192,
            prompt_price=0.0,
            completion_price=0.0,
        ),
        ModelInfo(
            id="other/thinker",
            name="Other Thinker",
            description="Reasons, but takes no pictures.",
            context_length=200_000,
            supports_thinking=True,
        ),
    ]
