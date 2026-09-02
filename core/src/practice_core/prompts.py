"""Rendering the shared grading prompt.

The template is read through :mod:`importlib.resources` and compiled from a
string rather than loaded from a directory. Jinja's ``FileSystemLoader`` needs
a real path, and inside an Android build this package lives in a zip that is
imported without ever being unpacked — so a loader that walks the filesystem
would work in the container and fail on the phone.
"""

import importlib.resources
from functools import lru_cache

from jinja2 import Environment, StrictUndefined, Template, UndefinedError

from practice_core.errors import ConfigurationError
from practice_core.grading import EvaluateAnswerInput

__all__ = ["EVALUATE_TEMPLATE", "render_evaluate_prompt"]

PROMPTS_DIR = "prompts"
EVALUATE_TEMPLATE = "evaluate.j2"


def _environment() -> Environment:
    """Return the Jinja environment the prompts are compiled in."""
    return Environment(
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        # Without this a variable the context does not supply renders as empty
        # text, so a renamed field silently produces a hollow prompt that the
        # provider still answers and still charges for.
        undefined=StrictUndefined,
    )


@lru_cache(maxsize=4)
def _template(name: str) -> Template:
    """Return a packaged template, compiled once per process.

    Args:
        name: The template's file name inside the ``prompts`` directory.

    Returns:
        The compiled template.

    Raises:
        ConfigurationError: If the template was not packaged.
    """
    resource = (
        importlib.resources.files(__package__ or "practice_core") / PROMPTS_DIR / name
    )
    try:
        source = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigurationError(f"prompt template {name} is not packaged") from exc
    return _environment().from_string(source)


def render_evaluate_prompt(context: EvaluateAnswerInput) -> str:
    """Render the prompt that grades one answer.

    Args:
        context: Everything the template interpolates.

    Returns:
        The prompt text.

    Raises:
        ConfigurationError: If the template asks for something the context does
            not carry, which is a mismatch to fix rather than a prompt to send.
    """
    try:
        return _template(EVALUATE_TEMPLATE).render(**context.model_dump())
    except UndefinedError as exc:
        raise ConfigurationError(
            f"{EVALUATE_TEMPLATE} needs a variable that "
            f"{type(context).__name__} does not provide"
        ) from exc
