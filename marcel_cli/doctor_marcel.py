"""Static, Marcel-owned checks used by ``marcel doctor``.

This module deliberately reads the configuration file directly.  In particular it
does not instantiate providers, refresh credentials, or contact the router.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from marcel_cli.doctor_report import Finding, check_fail, check_info, check_ok, check_warn


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_config(home: Path) -> dict[str, Any]:
    path = home / "config.yaml"
    if not path.exists():
        return {}
    try:
        return _mapping(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as exc:
        check_warn("Marcel configuration could not be read", f"({exc})")
        return {}


def _issue(finding: Finding, label: str, detail: str, hint: str) -> None:
    check_fail(label, detail)
    finding.manual_issues.append(hint)


def _provider_name(section: dict[str, Any]) -> str:
    return str(section.get("provider") or "").strip()


def _enabled_external_surfaces(config: dict[str, Any]) -> list[str]:
    """Return configured inbound surfaces without exposing credentials or endpoints."""
    surfaces: list[str] = []
    platforms = _mapping(config.get("platforms"))
    for name, section in platforms.items():
        if not isinstance(section, dict) or section.get("enabled") is not True:
            continue
        normalized = str(name).strip().lower()
        if normalized == "local":
            continue
        surfaces.append(normalized)

    # Email is configured by setup as an account profile rather than a platform.
    profiles = _mapping(config.get("accounts")).get("profiles", [])
    if isinstance(profiles, list) and any(
        isinstance(profile, dict)
        and profile.get("enabled", True) is not False
        and (profile.get("type") or profile.get("kind")) in {"imap_smtp", "google_workspace"}
        for profile in profiles
    ):
        surfaces.append("email")

    # Some deployments configure the web listener outside gateway.platforms.
    for key in ("web", "webhook", "web_server"):
        section = config.get(key)
        if isinstance(section, dict) and section.get("enabled") is True and key not in surfaces:
            surfaces.append(key)
    # Gateway setup stores several channel credentials in the profile .env rather
    # than config.yaml.  Presence is the same enablement gate used by startup.
    env_surfaces = {
        "telegram": ("TELEGRAM_BOT_TOKEN",),
        "discord": ("DISCORD_BOT_TOKEN",),
        "slack": ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"),
        "mattermost": ("MATTERMOST_URL", "MATTERMOST_TOKEN"),
        "matrix": ("MATRIX_HOMESERVER", "MATRIX_ACCESS_TOKEN", "MATRIX_USER_ID"),
        "signal": ("SIGNAL_HTTP_URL", "SIGNAL_ACCOUNT"),
        "whatsapp": ("WHATSAPP_ENABLED",),
        "email": ("EMAIL_ADDRESS", "EMAIL_PASSWORD"),
        "sms": ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"),
        "dingtalk": ("DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"),
        "feishu": ("FEISHU_APP_ID", "FEISHU_APP_SECRET"),
        "wecom": ("WECOM_BOT_ID",),
        "wecom_callback": ("WECOM_CALLBACK_CORP_ID", "WECOM_CALLBACK_AGENT_ID"),
        "weixin": ("WEIXIN_ACCOUNT_ID", "WEIXIN_TOKEN"),
        "webhook": ("WEBHOOK_ENABLED", "WEBHOOK_PORT"),
    }
    for label, env_names in env_surfaces.items():
        enabled = (
            any(os.environ.get(name) for name in env_names)
            if label in {"whatsapp", "webhook"}
            else all(os.environ.get(name) for name in env_names)
        )
        if enabled and label not in surfaces:
            surfaces.append(label)
    return sorted(set(surfaces))


def _check_execution_posture(config: dict[str, Any]) -> None:
    """Describe whether inbound input reaches a host-local execution backend."""
    terminal = _mapping(config.get("terminal"))
    backend = str(terminal.get("backend") or "local").strip().lower()
    surfaces = _enabled_external_surfaces(config)
    isolated_backends = {"docker", "singularity", "modal", "daytona", "vercel_sandbox"}
    isolated = backend in isolated_backends
    if isolated:
        check_ok("Marcel execution posture", f"({backend} whole-process isolation)")
    else:
        check_warn("Marcel execution posture", f"({backend or 'unknown'} backend; isolation not established)")
    if surfaces:
        check_info("External input surfaces enabled: " + ", ".join(surfaces))
        if not isolated:
            check_warn(
                "SECURITY WARNING: untrusted input can reach unsandboxed local execution",
                "(use whole-process OS isolation)",
            )
            check_info(
                "Allow-lists and approval prompts reduce access but are not a sandbox; "
                "run Marcel in a dedicated OS/container/VM boundary.",
            )
    else:
        check_info("External input surfaces enabled: none detected")


def run_marcel_static_checks(home: Path) -> Finding:
    """Print Marcel setup diagnostics without changing state or making calls."""
    finding = Finding()
    config = _read_config(home)
    marcel = _mapping(config.get("marcel"))
    if not marcel:
        _issue(finding, "Marcel identity and configuration", "(not configured)",
               "Run `marcel setup` to create Marcel configuration.")
        return finding

    _check_execution_posture(config)

    brand = _mapping(marcel.get("brand"))
    name = str(brand.get("name") or "").strip()
    if name == "Marcel":
        check_ok("Marcel identity and configuration", "(present)")
    else:
        _issue(finding, "Marcel identity and configuration", "(brand.name must be Marcel)",
               "Run `marcel setup` to restore Marcel identity configuration.")

    router = _mapping(marcel.get("router"))
    base_url = str(router.get("base_url") or "").strip()
    key_env = str(router.get("key_env") or "").strip()
    # Never include base URL or key values in output: even private endpoints may
    # contain credentials and environment values are always secrets.
    if base_url:
        check_ok("Marcel Routing API address", "(configured)")
    else:
        _issue(finding, "Marcel Routing API address", "(missing)",
               "Run `marcel setup` to configure Marcel Routing.")
    if key_env and os.environ.get(key_env):
        check_ok("Marcel Routing API key environment", "(present)")
    else:
        _issue(finding, "Marcel Routing API key environment", "(missing)",
               "Set the configured Marcel Routing key environment variable, then run `marcel doctor`.")

    routing = _mapping(marcel.get("routing"))
    strategy = routing.get("strategy")
    override = routing.get("allow_model_override")
    if strategy == "cheapest_capable" and override is True:
        check_ok("Marcel routing policy", "(cheapest capable; model overrides enabled)")
    else:
        _issue(finding, "Marcel routing policy", "(expected cheapest_capable with model overrides enabled)",
               "Run `marcel setup` to restore Marcel's routing defaults.")

    image, video = _mapping(config.get("image_gen")), _mapping(config.get("video_gen"))
    for label, section in (("Image provider", image), ("Video provider", video)):
        provider = _provider_name(section)
        if provider:
            check_ok(f"Marcel {label}", "(configured)")
        else:
            _issue(finding, f"Marcel {label}", "(not configured)",
                   f"Run `marcel setup` to configure a {label.lower()}.")

    tts, stt, voice = _mapping(config.get("tts")), _mapping(config.get("stt")), _mapping(config.get("voice"))
    if _provider_name(tts):
        check_ok("Marcel text-to-speech", "(configured)")
    else:
        _issue(finding, "Marcel text-to-speech", "(not configured)",
               "Run `marcel setup` to configure text-to-speech.")
    if _provider_name(stt):
        check_ok("Marcel speech-to-text", "(configured)")
    else:
        _issue(finding, "Marcel speech-to-text", "(not configured)",
               "Run `marcel setup` to configure speech-to-text.")
    if voice.get("audio_only") is True and voice.get("auto_tts") is True:
        check_ok("Marcel audio replies", "(audio-only defaults enabled)")
    else:
        _issue(finding, "Marcel audio replies", "(audio-only defaults are disabled)",
               "Run `marcel setup` to enable Marcel's audio reply defaults.")

    maintenance = _mapping(_mapping(config.get("memory")).get("maintenance"))
    welcome = home / "MARCEL_WELCOME.md"
    if maintenance.get("enabled") is True and maintenance.get("interval_hours"):
        check_ok("Marcel memory maintenance", "(configured)")
    else:
        _issue(finding, "Marcel memory maintenance", "(not configured)",
               "Run `marcel setup` to configure memory maintenance.")
    if welcome.is_file():
        check_ok("Marcel welcome card", "(present)")
    else:
        _issue(finding, "Marcel welcome card", "(missing)",
               "Run `marcel setup` to create the Marcel welcome card.")

    telegram = _mapping(_mapping(_mapping(config.get("display")).get("platforms")).get("telegram"))
    quiet = ("tool_progress", "interim_assistant_messages", "thinking_progress",
             "live_status", "long_running_notifications")
    if all(telegram.get(key) == "off" for key in quiet):
        check_ok("Marcel Telegram display", "(zero-noise settings enabled)")
    else:
        _issue(finding, "Marcel Telegram display", "(zero-noise settings incomplete)",
               "Run `marcel setup` to apply Marcel's Telegram zero-noise settings.")

    profiles = _mapping(config.get("accounts")).get("profiles", [])
    profiles = profiles if isinstance(profiles, list) else []
    pending = sum(1 for item in profiles if isinstance(item, dict)
                  and (item.get("enabled", True) is False or item.get("authorization_status") == "pending"))
    ready = len(profiles) - pending
    check_info(f"Marcel accounts: {ready} ready, {pending} pending")
    return finding