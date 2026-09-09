"""Focused static checks for the Marcel doctor surface."""

from __future__ import annotations

import contextlib
import io

import yaml

from marcel_cli.doctor_marcel import run_marcel_static_checks


def _marcel_config() -> dict:
    return {
        "marcel": {
            "brand": {"name": "Marcel"},
            "router": {"base_url": "https://router.example/v1", "key_env": "MARCEL_ROUTER_API_KEY"},
            "routing": {"strategy": "cheapest_capable", "allow_model_override": True},
        },
        "image_gen": {"provider": "gemini"},
        "video_gen": {"provider": "xai"},
        "tts": {"provider": "edge"},
        "stt": {"provider": "local"},
        "voice": {"auto_tts": True, "audio_only": True},
        "memory": {"maintenance": {"enabled": True, "interval_hours": 6}},
        "display": {"platforms": {"telegram": {
            "tool_progress": "off", "interim_assistant_messages": "off",
            "thinking_progress": "off", "live_status": "off",
            "long_running_notifications": "off",
        }}},
        "accounts": {"profiles": [
            {"authorization_status": "verified"},
            {"authorization_status": "pending"},
        ]},
    }


def test_marcel_static_checks_report_setup_without_secret_values(monkeypatch, tmp_path):
    secret = "not-for-doctor-output"
    monkeypatch.setenv("MARCEL_ROUTER_API_KEY", secret)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(_marcel_config()), encoding="utf-8")
    (tmp_path / "MARCEL_WELCOME.md").write_text("Welcome", encoding="utf-8")

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        finding = run_marcel_static_checks(tmp_path)

    rendered = output.getvalue()
    assert not finding.manual_issues
    assert "Marcel Routing API address" in rendered
    assert "Marcel accounts: 1 ready, 1 pending" in rendered
    assert secret not in rendered
    assert "router.example" not in rendered


def test_marcel_static_checks_are_read_only_when_setup_is_missing(tmp_path):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        finding = run_marcel_static_checks(tmp_path)

    assert finding.manual_issues == ["Run `marcel setup` to create Marcel configuration."]
    assert not list(tmp_path.iterdir())