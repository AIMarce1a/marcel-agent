"""``marcel doctor`` subcommand parser."""

from __future__ import annotations

import os
import sys
from typing import Callable


def build_doctor_parser(subparsers, *, cmd_doctor: Callable) -> None:
    """Attach the ``doctor`` subcommand to ``subparsers``."""
    command = "marcel" if os.path.basename(sys.argv[0]).lower().startswith("marcel") else "marcel"
    product = "Marcel" if command == "marcel" else "Marcel Agent"
    doctor_parser = subparsers.add_parser(
        "doctor", help="Check configuration and dependencies",
        description=f"Diagnose issues with {product} setup")
    doctor_parser.add_argument(
        "--fix", action="store_true", help="Attempt to fix issues automatically")
    doctor_parser.add_argument(
        "--live", action="store_true",
        help="Opt-in: run one bounded, read-only real-call health probe per "
            "configured tool backend (Firecrawl/FAL/browser/MCP/TTS/STT) "
            "after the static checks. Makes real network calls.")
    doctor_parser.add_argument(
        "--ack", metavar="ADVISORY_ID", default=None,
        help="Acknowledge a security advisory by ID and exit. After ack, the "
            f"advisory will no longer trigger startup banners. Run `{command} "
            "doctor` first to see active advisories and their IDs.")
    doctor_parser.set_defaults(func=cmd_doctor)
