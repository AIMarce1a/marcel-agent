#!/usr/bin/env python3
"""Validate the credential-free, pristine ``marcel doctor`` qualification."""

from __future__ import annotations

import re
import sys
from pathlib import Path

IDENTITY = "✗ Marcel identity and configuration (not configured)"
SUMMARY = "Found 2 issue(s) to address:"
EXPECTED_ISSUES = (
    "1. Run 'marcel doctor --fix' or 'marcel setup' to migrate config",
    "2. Run `marcel setup` to create Marcel configuration.",
)
REQUIRED_PACKAGES = (
    "✓ OpenAI SDK",
    "✓ Rich (terminal UI)",
    "✓ python-dotenv",
    "✓ PyYAML",
    "✓ HTTPX",
)
OUTDATED = re.compile(
    r"⚠ Config version outdated \(v0 → v[0-9]+\) \(new settings available\)"
)
NUMBERED = re.compile(r"^\d+\. ")


def validate(text: str, status: int) -> None:
    """Raise ``ValueError`` unless doctor is exactly the expected state."""
    if status not in (0, 1):
        raise ValueError(f"unexpected marcel doctor exit code: {status}")
    if re.search(r"(?i)traceback|exception|fatal", text):
        raise ValueError("doctor output contains traceback/exception/fatal")

    lines = [line.strip() for line in text.splitlines()]
    if [line for line in lines if "✗" in line] != [IDENTITY]:
        raise ValueError("doctor must contain exactly one expected cross line")
    if any(re.match(r"(?i)^(?:FAIL(?:URE)?|ERROR)\b", line) for line in lines):
        raise ValueError("doctor output contains an unexpected failure line")
    if lines.count(SUMMARY) != 1:
        raise ValueError("doctor summary is missing or duplicated")
    numbered = [line for line in lines if NUMBERED.match(line)]
    if numbered != list(EXPECTED_ISSUES):
        raise ValueError("doctor numbered issues are missing, duplicated, or reordered")
    if sum(bool(OUTDATED.fullmatch(line)) for line in lines) != 1:
        raise ValueError("doctor must contain exactly one config-version warning")
    if lines.count("◆ Required Packages") != 1:
        raise ValueError("Required Packages section is missing or duplicated")
    if any(lines.count(row) != 1 for row in REQUIRED_PACKAGES):
        raise ValueError("required package rows are missing or duplicated")
    # The tip is the terminal diagnostic summary. Requiring it rejects output
    # that was truncated immediately after the numbered issues.
    tip = "Tip: run 'marcel doctor --fix' to auto-fix what's possible."
    if lines.count(tip) != 1:
        raise ValueError("doctor summary is truncated or duplicated")
    if not lines or [line for line in lines if line][-1] != tip:
        raise ValueError("doctor output has trailing or truncated content")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} DOCTOR_OUTPUT EXIT_STATUS", file=sys.stderr)
        return 2
    try:
        validate(Path(argv[1]).read_text(encoding="utf-8"), int(argv[2]))
    except (OSError, ValueError) as exc:
        print(f"doctor qualification rejected: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))