"""Resolve MARCEL_HOME for standalone skill scripts.

Skill scripts may run outside the Marcel process (system Python, nix env,
CI) where ``marcel_constants`` is not importable.  This module provides the
same ``get_marcel_home()`` contract without requiring it on ``sys.path``.

When ``marcel_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from marcel_constants import get_marcel_home as get_marcel_home
except (ModuleNotFoundError, ImportError):

    def get_marcel_home() -> Path:
        """Return the Marcel home directory (default: ``~/.marcel``)."""
        val = os.environ.get("MARCEL_HOME", "").strip()
        return Path(val) if val else Path.home() / ".marcel"
