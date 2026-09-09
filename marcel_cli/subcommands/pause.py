"""``marcel pause`` / ``marcel resume`` — the global emergency stop.

``pause`` writes the ESTOP sentinel at ``$MARCEL_HOME/ESTOP``; cron, kanban and new gateway
turns halt on their next check (in-flight work is never killed). ``resume`` removes it and
operation resumes on the next tick — no restart. Ported from gastownhall/gastown estop.go (MIT).
"""

from __future__ import annotations

import argparse
import os
import sys


def _display_identity() -> tuple[str, str]:
    command = "marcel" if os.path.basename(sys.argv[0]).lower().startswith("marcel") else "marcel"
    return command, "Marcel" if command == "marcel" else "Marcel"


def cmd_pause(args: argparse.Namespace) -> int:
    """Engage the global emergency stop."""
    from agent.estop import engage, get_state, is_engaged

    reason = getattr(args, "reason", None)
    already = is_engaged()
    path = engage(reason=reason)
    state = get_state() or {}
    command, brand = _display_identity()
    verb = "Still paused" if already else f"{brand} paused"
    detail = f" — reason: {state['reason']}" if state.get("reason") else ""
    print(f"⏸️  {verb}{detail}")
    print(f"    sentinel: {path}")
    print(
        "    Cron dispatch, kanban dispatch, and new gateway turns are on hold.\n"
        f"    In-flight work keeps running. Run `{command} resume` to lift the pause.")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Disengage the global emergency stop."""
    from agent.estop import disengage, sentinel_path

    _, brand = _display_identity()
    if disengage():
        print(f"▶️  {brand} resumed — dispatch picks up on the next tick.")
    else:
        print(f"{brand} is not paused (no sentinel at {sentinel_path()}).")
    return 0


def build_pause_parser(subparsers) -> None:
    """Attach the ``pause`` and ``resume`` subcommands to ``subparsers``."""
    command, _ = _display_identity()
    pause_parser = subparsers.add_parser(
        "pause", help="Emergency stop: pause cron/kanban dispatch and new gateway turns",
        description="Engage the global emergency stop. Halts NEW work only — cron "
            "dispatch, kanban dispatch, and new gateway turns — until "
            f"`{command} resume`. In-flight work is never killed.")
    pause_parser.add_argument(
        "--reason", default=None, help="Optional reason stored in the sentinel and shown to users")
    pause_parser.set_defaults(func=cmd_pause)

    resume_parser = subparsers.add_parser(
        "resume", help=f"Lift the emergency stop set by `{command} pause`",
        description="Remove the ESTOP sentinel; dispatch resumes on the next tick.")
    resume_parser.set_defaults(func=cmd_resume)
