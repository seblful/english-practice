"""The models the bot works with, grouped by what they describe.

- ``auth``: who may use the bot — the only content model that is the bot's own.
- ``agents``: the inputs and outputs of its LLM calls.

The practice content itself is not here. Units, exercises, questions and
answers come from :mod:`practice_core.models`, shared with the Android app, and
are imported from there directly rather than through a shim in this package —
one name for one model.

That rule applies to the two submodules above as well, which is why this file
re-exports nothing: every importer names the submodule it wants.
"""
