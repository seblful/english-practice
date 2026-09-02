"""Rendering the prompts that ship inside a package.

Every prompt in the project renders through here: the grading prompt this
package owns, the bot's assistant prompt, and the pipeline's extraction
prompts. Each names its own package as the anchor, so a prompt lives next to
the agent that sends it while the rendering rules — strict undefined variables,
one compiled template per process — are written once.

The template is compiled from text read out of the package rather than loaded
from a directory. Jinja's ``FileSystemLoader`` needs a real path, and inside an
Android build a package lives in a zip that is never unpacked, so a
filesystem loader would work in the container and fail on the phone.
"""

from functools import lru_cache

from jinja2 import Environment, StrictUndefined, Template, UndefinedError
from pydantic import BaseModel

from practice_core.errors import ConfigurationError
from practice_core.resources import read_packaged_text

__all__ = ["PROMPTS_DIR", "compiled_template", "render_packaged_template"]

# Every package keeps its prompts in the same place, so an agent only has to
# name the file.
PROMPTS_DIR = "prompts"


def _environment() -> Environment:
    """Return the Jinja environment every prompt is compiled in."""
    return Environment(
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        # Without this a variable the context does not supply renders as empty
        # text, so a renamed field silently produces a hollow prompt that the
        # provider still answers and still charges for.
        undefined=StrictUndefined,
    )


@lru_cache(maxsize=16)
def compiled_template(anchor: str, name: str) -> Template:
    """Return a packaged prompt template, compiled once per process.

    Args:
        anchor: Import name of the package holding ``prompts/``.
        name: The template's file name inside that directory.

    Returns:
        The compiled template.

    Raises:
        ConfigurationError: If the template was not packaged.
    """
    try:
        source = read_packaged_text(anchor, PROMPTS_DIR, name)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ConfigurationError(f"prompt template {name} is not packaged") from exc
    return _environment().from_string(source)


def render_packaged_template(anchor: str, name: str, context: BaseModel) -> str:
    """Render a packaged prompt with a validated context.

    Args:
        anchor: Import name of the package holding ``prompts/``.
        name: The template's file name inside that directory.
        context: Pydantic model holding the template's variables.

    Returns:
        The prompt text.

    Raises:
        ConfigurationError: If the template was not packaged, or if it asks for
            something the context does not carry — a mismatch to fix rather
            than a prompt to send.
    """
    try:
        return compiled_template(anchor, name).render(**context.model_dump())
    except UndefinedError as exc:
        raise ConfigurationError(
            f"{name} needs a variable that {type(context).__name__} does not provide"
        ) from exc
