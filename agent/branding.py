"""Runtime branding for user-facing text.

The Marcel module, environment, and storage names are compatibility contracts.
Only presentation follows the executable the user chose: ``marcel`` presents
Marcel, while the legacy ``marcel`` executable retains its historical output.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Sequence


def is_marcel_invocation(argv: Sequence[str] | None = None) -> bool:
    """Whether this process was launched through the public ``marcel`` command."""
    if argv is None and os.environ.get("MARCEL_BRANDING") == "1":
        return True
    effective_argv = argv if argv is not None else sys.argv
    executable = effective_argv[0] if effective_argv else ""
    return os.path.basename(executable).lower().startswith("marcel")


def runtime_brand(argv: Sequence[str] | None = None) -> str:
    """Return the public product name appropriate for this invocation."""
    return "Marcel" if is_marcel_invocation(argv) else "Marcel"


def runtime_command(command: str = "", argv: Sequence[str] | None = None) -> str:
    """Return a user-copyable command without changing internal command aliases."""
    entrypoint = "marcel" if is_marcel_invocation(argv) else "marcel"
    return f"{entrypoint} {command}".rstrip()


def brand_user_facing_text(text: str, argv: Sequence[str] | None = None) -> str:
    """Apply the Marcel presentation name to catalog text, never to identifiers.

    Catalog/model values are prose. Public command examples are rewritten and
    legacy private storage paths are described without exposing the internal
    compatibility brand.
    """
    if not is_marcel_invocation(argv):
        return text
    branded = text.replace("Marcel Agent", "Marcel").replace("Marcel", "Marcel")
    branded = re.sub(r"(?<![./~\w-])marcel(?=\s+[a-z])", "marcel", branded)
    branded = re.sub(
        r"(?:~|/home/[^/\s]+)/(?:\.marcel)(?:/\.env)?",
        "the Marcel private configuration store",
        branded,
    )
    return branded


__all__ = [
    "brand_user_facing_text",
    "is_marcel_invocation",
    "runtime_brand",
    "runtime_command",
]