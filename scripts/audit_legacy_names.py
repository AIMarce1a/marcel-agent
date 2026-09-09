#!/usr/bin/env python3
"""Reject unreviewed legacy product names.

Each exception requires both a path matcher and a content matcher.  External
coordinates remain usable until Marcel infrastructure exists; migration code
must recognize historical on-disk identifiers; attribution stays immutable.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = re.compile(r"hermes", re.IGNORECASE)
EXECUTABLE_COORDINATE_FILES = {
    "scripts/install.sh",
    "scripts/install.ps1",
    "apps/desktop/electron/bootstrap-runner.ts",
    "apps/bootstrap-installer/src-tauri/src/install_script.rs",
}
OFFICIAL_COORDINATE_CONTEXT = re.compile(
    r"(?:update_cmd_(?:git|zip)\.py|install\.(?:sh|ps1)|"
    r"bootstrap(?:-runner)?\.ts|install_script\.rs|apps/desktop/README\.md|"
    r"send-diagnostics-dialog\.tsx|about-settings\.tsx|components/onboarding/)"
)
UPSTREAM_EXECUTABLE_URL = re.compile(
    r"(?:raw\.githubusercontent\.com|github\.com)/NousResearch/hermes-agent"
)

# (path glob, permitted content regex, reason)
ALLOW = [
    ("marcel_migration.py", re.compile(r"HERMES_HOME|\.hermes|/hermes|\\hermes|Hermes|hermes"), "home migration"),
    (
        "apps/desktop/electron/legacy-user-data-migration.ts",
        re.compile(r"hermes-desktop|Hermes"),
        "Electron userData migration",
    ),
    ("UPSTREAM.md", LEGACY, "upstream provenance"),
    ("LICENSE", LEGACY, "MIT attribution"),
    ("**/LICENSE", LEGACY, "bundled third-party attribution"),
    ("contributors/emails/**", LEGACY, "immutable contributor identity"),
    (
        "scripts/release.py",
        re.compile(
            r"(?:pi@hermes\.local|kavi@local\.hermes|hermes\.wanderer@yahoo\.com|"
            r"jason@hermes-jc|hermes@(?:marian\.local|nousresearch\.com|noushq\.ai|example\.com)|"
            r"agent@hermes\.local|teknium@hermes-agent|github@nadyahermes\.anonaddy\.com|"
            r"hermesagent26|vigo@hermes|hex\.hermes@agentmail\.to|zhchl@hermes-agent\.local|"
            r"274096618\+hermes-agent-dhabibi)"
        ),
        "immutable release contributor identity",
    ),
    (
        "scripts/contributor_audit.py",
        re.compile(r"hermes@(?:nousresearch\.com|habibilabs\.dev)|hermes-audit@example\.com|hermes-seaeye"),
        "immutable contributor-audit identity",
    ),
    ("scripts/audit_legacy_names.py", LEGACY, "the audit's own match rules"),
    (
        "*",
        re.compile(
            r"(?:NousResearch/hermes-agent|nousresearch/hermes-agent|"
            r"(?:setup\.)?hermes-agent\.nousresearch\.com|"
            r"nousresearch\.github\.io/hermes-agent|"
            r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
            r"(?:NousResearch|nousresearch)/hermes-agent|"
            r"https?://hermes-agent\.com)"
        ),
        "unprovisioned upstream infrastructure coordinate",
    ),
    (
        "*",
        re.compile(
            r"hermes-(?:estree|parser|example-plugins|media-studio|telegram-business)|"
            r"HermesClaw|hermesclaw|sample-hermes-agent"
        ),
        "immutable external project/package name",
    ),
]


def unreviewed_remainder(path: str, line: str) -> str:
    remainder = line
    for glob, pattern, _reason in ALLOW:
        if fnmatch.fnmatch(path, glob):
            remainder = pattern.sub("", remainder)
    return remainder


def main() -> int:
    files = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    violations: list[str] = []
    for relative in files:
        path = ROOT / relative
        if not path.is_file():
            continue
        if LEGACY.search(relative) and not (
            fnmatch.fnmatch(relative, "contributors/emails/**")
            and re.fullmatch(r"contributors/emails/[^/]*hermes[^/]*", relative, re.IGNORECASE)
        ):
            violations.append(f"{relative}:legacy-filename")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if relative in EXECUTABLE_COORDINATE_FILES and UPSTREAM_EXECUTABLE_URL.search(text):
            violations.append(f"{relative}:upstream-executable-download")
        if OFFICIAL_COORDINATE_CONTEXT.search(relative) and UPSTREAM_EXECUTABLE_URL.search(text):
            violations.append(f"{relative}:upstream-official-coordinate")
        for number, line in enumerate(text.splitlines(), 1):
            if LEGACY.search(unreviewed_remainder(relative, line)):
                violations.append(f"{relative}:{number}")
    if violations:
        print("Unreviewed legacy product name(s):")
        print("\n".join(violations))
        return 1
    print("Legacy-name audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())