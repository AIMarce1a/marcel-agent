"""Resolve MARCEL_HOME for standalone skill scripts.

Skill scripts may run outside the Marcel process (e.g. system Python,
nix env, CI) where ``marcel_constants`` is not importable.  This module
provides the same ``get_marcel_home()`` and ``display_marcel_home()``
contracts as ``marcel_constants`` without requiring it on ``sys.path``.

When ``marcel_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``marcel_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``MARCEL_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from marcel_constants import display_marcel_home as display_marcel_home
    from marcel_constants import get_marcel_home as get_marcel_home
except (ModuleNotFoundError, ImportError):

    def get_marcel_home() -> Path:
        """Return the Marcel home directory (default: ~/.marcel).

        Mirrors ``marcel_constants.get_marcel_home()``."""
        val = os.environ.get("MARCEL_HOME", "").strip()
        return Path(val) if val else Path.home() / ".marcel"

    def display_marcel_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``marcel_constants.display_marcel_home()``."""
        home = get_marcel_home()
        try:
            return "~/" + home.relative_to(Path.home()).as_posix()
        except ValueError:
            return str(home)
