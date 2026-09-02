"""English Practice Bot - Telegram application for English grammar practice."""

from importlib.metadata import version

from english_practice.settings import get_settings

__version__ = version("english-practice")
__author__ = "Aliaksei Chymba"
__email__ = "alesha.chimba@gmail.com"

__all__ = [
    "__author__",
    "__email__",
    "__version__",
    "get_settings",
]
