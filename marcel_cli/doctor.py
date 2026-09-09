"""``marcel doctor`` — diagnose (and with --fix, repair) a Marcel install.

``run_doctor`` walks ``DOCTOR_CHECKS`` in order; each check prints its own rows and returns a ``Finding``.
Check bodies live in the ``doctor_*`` siblings.
"""

import os
import sys
import builtins
from contextlib import contextmanager

from marcel_cli.config import get_env_path, get_marcel_home, get_project_root
from marcel_cli.env_loader import load_marcel_dotenv
from marcel_constants import display_marcel_home

PROJECT_ROOT = get_project_root()
MARCEL_HOME = get_marcel_home()
_DHH = display_marcel_home()  # user-facing display path (e.g. ~/.marcel or ~/.marcel/profiles/coder)

# Load environment variables from ~/.marcel/.env so API key checks work
_env_path = get_env_path()
load_marcel_dotenv(marcel_home=_env_path.parent, project_env=PROJECT_ROOT / ".env")

from marcel_cli.colors import Colors, color
from marcel_cli.doctor_report import Finding, _section, check_bool, check_info, doctor_check, warn_on_error
from marcel_cli.doctor_connectivity import _has_healthy_oauth_fallback_for_apikey_provider, build_probes, run_probes
from marcel_cli.doctor_tools import _safe_which

from marcel_cli.doctor_config import (
    _check_config_drift,
    _check_config_file,
    _check_env_file,
    _check_mcp_security,
    _check_xai_retirement,
    _check_plugin_compat,
)
from marcel_cli.doctor_platform import (
    _check_certificates,
    _check_command_installation,
    _check_gateway_supervision,
    _check_python_environment,
    _check_required_packages,
    _check_security_advisories,
)
from marcel_cli.doctor_tools import (
    _check_git_and_rg,
    _check_node_and_browser,
    _check_npm_audit,
    _check_terminal_backend,
    _check_tool_availability,
)
from marcel_cli.doctor_state import (
    _check_directory_structure,
    _check_memory_provider,
    _check_profiles,
    _check_skills_hub,
    _check_state_db,
)

_PROVIDER_ENV_HINTS = (
    "DEEPINFRA_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
    "OPENAI_BASE_URL", "NOUS_API_KEY", "GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY", "KIMI_API_KEY",
    "KIMI_CN_API_KEY", "GMI_API_KEY", "FIREWORKS_API_KEY", "ACTUAL_API_KEY", "ACTUAL_BASE_URL", "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY", "KILOCODE_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "HF_TOKEN",
    "AI_GATEWAY_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY", "COMMANDCODE_API_KEY", "XIAOMI_API_KEY",
    "TOKENHUB_API_KEY", "TOKENPLAN_API_KEY",
)


@doctor_check()
def _check_auth_providers(should_fix: bool, f: Finding) -> None:
    """Refresh-free OAuth status snapshot (doctor must never trigger a token refresh)."""
    with warn_on_error("Auth provider status", "(could not check: {e})"):
        from marcel_cli.auth import get_nous_auth_status_local, get_codex_auth_status, get_minimax_oauth_auth_status
        _login_row("Nous Portal auth", get_nous_auth_status_local())
        # Native OAuth is Marcel' own device-code flow; the Codex CLI only imports existing ~/.codex/auth.json
        # tokens, so the hint sits under the Codex row (not as another provider's remedy).
        if not _login_row("OpenAI Codex auth", get_codex_auth_status(), show_error=True) and not _safe_which("codex"):
            check_info("codex CLI not installed (optional — only required to import tokens from an existing Codex CLI login)")
        minimax_status = get_minimax_oauth_auth_status()
        _login_row("MiniMax OAuth", minimax_status, f"(logged in, region={minimax_status.get('region', 'global')})")
    with warn_on_error(""):  # xAI OAuth separately, so an import failure cannot disrupt the rows already printed
        from marcel_cli.auth import get_xai_oauth_auth_status
        _login_row("xAI OAuth", get_xai_oauth_auth_status() or {}, show_error=True)


def _login_row(label: str, status: dict, ok_detail: str = "(logged in)", show_error: bool = False) -> bool:
    """ok/warn row for an OAuth status dict; with show_error, its ``error`` hint prints under a not-logged-in row."""
    logged_in = check_bool(status.get("logged_in"), (label, ok_detail), (label, "(not logged in)"))
    if not logged_in and show_error and status.get("error"):
        check_info(status["error"])
    return logged_in


@doctor_check()
def _check_api_connectivity(should_fix: bool, f: Finding) -> None:
    """Parallel HTTP/SDK probes for every configured provider; results printed in submission order."""
    probes = build_probes()
    # Single status line so users see something happening; ``\r`` clears it once results land.
    print(f"  {color(f'Running {len(probes)} connectivity checks in parallel…', Colors.DIM)}", end="", flush=True)
    results = run_probes(probes)
    print("\r" + " " * 70 + "\r", end="")
    for r in results:
        for glyph, label, detail in r.lines:
            print(f"  {glyph} {label}" + (f" {detail}" if detail else ""))
        if r.issues and not _has_healthy_oauth_fallback_for_apikey_provider(r.label):
            f.issues.extend(r.issues)


# Ordered (section title, check). None title = check prints its own header (or none); order is user-visible.
DOCTOR_CHECKS = (
    ('Security Advisories', _check_security_advisories), ('MCP Server Security', _check_mcp_security),
    ('Python Environment', _check_python_environment), ('SSL / CA Certificates', _check_certificates),
    ('Required Packages', _check_required_packages), ('Configuration Files', _check_env_file),
    (None, _check_config_file), (None, _check_config_drift),
    ('xAI Model Retirement (May 15, 2026)', _check_xai_retirement),
    ('Plugin import paths (removed Sep 14, 2026)', _check_plugin_compat), ('Auth Providers', _check_auth_providers),
    ('Directory Structure', _check_directory_structure), (None, _check_state_db),
    (None, _check_gateway_supervision), (None, _check_command_installation),
    ('External Tools', _check_git_and_rg), (None, _check_terminal_backend), (None, _check_node_and_browser),
    (None, _check_npm_audit), ('API Connectivity', _check_api_connectivity),
    ('Tool Availability', _check_tool_availability), ('Skills Hub', _check_skills_hub),
    ('Memory Provider', _check_memory_provider), (None, _check_profiles),
)


def _ack_advisory(ack_target: str) -> None:
    """`marcel doctor --ack <id>`: persist the ack and return without running diagnostics."""
    from marcel_cli.security_advisories import ADVISORIES, ack_advisory
    valid_ids = {a.id for a in ADVISORIES}
    if ack_target not in valid_ids:
        print(color(f"Unknown advisory ID: {ack_target!r}. Known IDs: {', '.join(sorted(valid_ids)) or '(none)'}", Colors.RED))
        sys.exit(2)
    if ack_advisory(ack_target):
        print(color(f"  ✓ Acknowledged advisory {ack_target}. It will no longer trigger startup banners.", Colors.GREEN))
    else:
        print(color(f"  ✗ Failed to persist ack for {ack_target}. Check ~/.marcel/config.yaml is writable.", Colors.RED))
        sys.exit(1)


def _print_summary(should_fix: bool, total: Finding) -> None:
    print()
    remaining = total.issues + total.manual_issues
    numbered = "".join(f"  {i}. {issue}\n" for i, issue in enumerate(remaining, 1))
    if should_fix and total.fixed > 0:
        print(color("─" * 60, Colors.GREEN))
        print(color(f"  Fixed {total.fixed} issue(s).", Colors.GREEN, Colors.BOLD), end="")
        print(color(f" {len(remaining)} issue(s) require manual intervention.", Colors.YELLOW, Colors.BOLD) if remaining else "")
        print()
        if remaining:
            print(numbered)
    elif remaining:
        print(color("─" * 60, Colors.YELLOW))
        print(color(f"  Found {len(remaining)} issue(s) to address:", Colors.YELLOW, Colors.BOLD))
        print()
        print(numbered)
        if not should_fix:
            command = "marcel" if _is_marcel_invocation() else "marcel"
            print(color(f"  Tip: run '{command} doctor --fix' to auto-fix what's possible.", Colors.DIM))
    else:
        print(color("─" * 60, Colors.GREEN))
        print(color("  All checks passed! 🎉", Colors.GREEN, Colors.BOLD))
    print()


def _is_marcel_invocation() -> bool:
    return os.path.basename(sys.argv[0]).lower().startswith("marcel")


@contextmanager
def _marcel_output_branding(enabled: bool):
    """Brand generic doctor hints while retaining Marcel internal identifiers."""
    if not enabled:
        yield
        return
    original_print = builtins.print
    def branded_print(*values, **kwargs):
        values = tuple(
            value.replace("marcel doctor", "marcel doctor").replace("marcel setup", "marcel setup")
            if isinstance(value, str) else value
            for value in values
        )
        original_print(*values, **kwargs)
    builtins.print = branded_print
    try:
        yield
    finally:
        builtins.print = original_print


def run_doctor(args):
    """Run diagnostic checks."""
    should_fix = getattr(args, 'fix', False)
    # Doctor runs from the interactive CLI, so CLI-gated tool checks (e.g. cronjob) see the same context.
    os.environ.setdefault("MARCEL_INTERACTIVE", "1")
    if getattr(args, 'ack', None):
        return _ack_advisory(args.ack)
    marcel = _is_marcel_invocation()
    with _marcel_output_branding(marcel):
        print()
        title = "Marcel" if marcel else "Marcel"
        for line in ("┌─────────────────────────────────────────────────────────┐",
                     f"│                 🩺 {title} Doctor{' ' * (25 - len(title))}│",
                     "└─────────────────────────────────────────────────────────┘"):
            print(color(line, Colors.CYAN))
        total = Finding()
        for section, check in DOCTOR_CHECKS:
            # Marcel's normal doctor is deterministic and offline. Provider
            # connectivity belongs behind the explicit --live opt-in.
            if marcel and check is _check_api_connectivity and not getattr(args, 'live', False):
                continue
            if section:
                _section(section)
            total.merge(check(should_fix))
        if marcel:
            _section("Marcel Setup")
            from marcel_cli.doctor_marcel import run_marcel_static_checks
            total.merge(run_marcel_static_checks(MARCEL_HOME))
        # Opt-in live probes run AFTER all static checks (`--live`: real network calls; bounded + read-only).
        with warn_on_error(""):
            from marcel_cli.doctor_live import maybe_run_live_checks
            maybe_run_live_checks(args, total.manual_issues)
        _print_summary(should_fix, total)


# ---- BEGIN PLUGIN-COMPAT (revert-scheduled; see COMPAT_MANIFEST.md) ----
# Names external plugins imported from this module before the Sep 2026 decomposition.
# Internal code MUST NOT use these (scripts/check_compat_pointers.py fails CI if it does).
# The whole block is removed by reverting the commit that added it.
from pathlib import Path  # noqa: F401,E402
import importlib.util  # noqa: F401,E402
import shutil  # noqa: F401,E402
import subprocess  # noqa: F401,E402

def check_fail(text: str, detail: str = ""):
    print(f"  {color('✗', Colors.RED)} {text}" + (f" {color(detail, Colors.DIM)}" if detail else ""))

def check_ok(text: str, detail: str = ""):
    print(f"  {color('✓', Colors.GREEN)} {text}" + (f" {color(detail, Colors.DIM)}" if detail else ""))

def check_warn(text: str, detail: str = ""):
    print(f"  {color('⚠', Colors.YELLOW)} {text}" + (f" {color(detail, Colors.DIM)}" if detail else ""))


_PLUGIN_COMPAT_LAZY = {
    'FTS_STORAGE_VERSION': ('marcel_state_common', 'FTS_STORAGE_VERSION'),
    'OPENROUTER_MODELS_URL': ('marcel_constants', 'OPENROUTER_MODELS_URL'),
    'STATE_DB_SIZE_WARN_BYTES': ('marcel_cli.doctor_state', 'STATE_DB_SIZE_WARN_BYTES'),
    'agent_browser_runnable': ('marcel_constants', 'agent_browser_runnable'),
    'base_url_host_matches': ('utils', 'base_url_host_matches'),
    'check_certificates': ('marcel_cli.doctor_platform', 'check_certificates'),
    'check_macos_full_disk_access': ('marcel_cli.doctor_platform', 'check_macos_full_disk_access'),
    'check_macos_tcc_anchor': ('marcel_cli.doctor_platform', 'check_macos_tcc_anchor'),
    'check_macos_tcc_grants': ('marcel_cli.doctor_platform', 'check_macos_tcc_grants'),
    'collect_deprecated_config_keys': ('marcel_cli.doctor_config', 'collect_deprecated_config_keys'),
    'collect_deprecated_env_vars': ('marcel_cli.doctor_config', 'collect_deprecated_env_vars'),
    'collect_relay_plugin_cutover_findings': ('marcel_cli.doctor_config', 'collect_relay_plugin_cutover_findings'),
    'describe_vercel_auth': ('marcel_cli.vercel_auth', 'describe_vercel_auth'),
    'detect_install_method': ('marcel_cli.config', 'detect_install_method'),
    'is_nix_install_method': ('marcel_cli.config', 'is_nix_install_method'),
    'managed_scope_check': ('marcel_cli.doctor_config', 'managed_scope_check'),
    'recommended_update_command_for_method': ('marcel_cli.config', 'recommended_update_command_for_method'),
    'report_deprecated_config_and_env': ('marcel_cli.doctor_config', 'report_deprecated_config_and_env'),
}


def __getattr__(name):  # PEP 562 — lazy so no import cycles
    target = _PLUGIN_COMPAT_LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    from marcel_cli.plugin_compat import warn_once
    warn_once(__name__, name, *target)
    return getattr(importlib.import_module(target[0]), target[1])
# ---- END PLUGIN-COMPAT ----
