"""Tests for rendering prompts that ship inside a package."""

import pytest
from pydantic import BaseModel

from practice_core.errors import ConfigurationError
from practice_core.resources import read_packaged_text
from practice_core.templates import compiled_template, render_packaged_template

ANCHOR = "practice_core"
TEMPLATE = "evaluate.j2"


class _Context(BaseModel):
    question_number: str


class TestReadPackagedText:
    def test_reads_a_file_that_travels_with_the_package(self) -> None:
        text = read_packaged_text(ANCHOR, "prompts", TEMPLATE)

        assert "QuestionNumber" in text

    def test_a_file_that_was_not_packaged(self) -> None:
        with pytest.raises(FileNotFoundError, match=r"absent\.j2"):
            read_packaged_text(ANCHOR, "prompts", "absent.j2")

    def test_a_package_that_does_not_exist(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            read_packaged_text("practice_nowhere", "prompts", TEMPLATE)


class TestCompiledTemplate:
    def test_compiled_once_per_template(self) -> None:
        """Recompiling a prompt on every call would parse it thousands of times."""
        assert compiled_template(ANCHOR, TEMPLATE) is compiled_template(
            ANCHOR, TEMPLATE
        )

    def test_a_template_that_was_not_packaged(self) -> None:
        with pytest.raises(ConfigurationError, match="not packaged"):
            compiled_template(ANCHOR, "absent.j2")

    def test_a_package_that_does_not_exist(self) -> None:
        with pytest.raises(ConfigurationError, match="not packaged"):
            compiled_template("practice_nowhere", TEMPLATE)


class TestRenderPackagedTemplate:
    def test_a_context_the_template_does_not_fit_is_an_error(self) -> None:
        """A renamed field used to yield a hollow prompt the provider billed for."""
        with pytest.raises(ConfigurationError, match=r"evaluate\.j2 needs a variable"):
            render_packaged_template(ANCHOR, TEMPLATE, _Context(question_number="3"))
