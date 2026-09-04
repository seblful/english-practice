"""Rendering the prompts that ship inside a package."""

from functools import lru_cache

from jinja2 import Environment, StrictUndefined, Template, UndefinedError
from pydantic import BaseModel

from practice_core.errors import ConfigurationError
from practice_core.resources import read_packaged_text

__all__ = ["PROMPTS_DIR", "compiled_template", "render_packaged_template"]

# Every package keeps its prompts in the same place, so an agent names a file.
PROMPTS_DIR = "prompts"


def _environment() -> Environment:
    """Return the Jinja environment every prompt is compiled in."""
    return Environment(
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        # Without this a missing variable renders empty, and the provider charges.
        undefined=StrictUndefined,
    )


@lru_cache(maxsize=16)
def compiled_template(anchor: str, name: str) -> Template:
    """Return a packaged prompt template, compiled once per process."""
    try:
        source = read_packaged_text(anchor, PROMPTS_DIR, name)
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ConfigurationError(f"prompt template {name} is not packaged") from exc
    return _environment().from_string(source)


def render_packaged_template(anchor: str, name: str, context: BaseModel) -> str:
    """Render a packaged prompt with a validated context."""
    try:
        return compiled_template(anchor, name).render(**context.model_dump())
    except UndefinedError as exc:
        raise ConfigurationError(
            f"{name} needs a variable that {type(context).__name__} does not provide"
        ) from exc
