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
    before = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        finding = run_marcel_static_checks(tmp_path)

    assert finding.manual_issues == ["Run `marcel setup` to create Marcel configuration."]
    after = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
    )
    assert after == before


def test_marcel_static_checks_warn_for_external_input_on_local_execution(monkeypatch, tmp_path):
    config = _marcel_config()
    config["terminal"] = {"backend": "local"}
    config["platforms"] = {
        "telegram": {"enabled": True},
        "webhook": {"enabled": True},
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (tmp_path / "MARCEL_WELCOME.md").write_text("Welcome", encoding="utf-8")
    monkeypatch.setenv("MARCEL_ROUTER_API_KEY", "present")

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_marcel_static_checks(tmp_path)

    rendered = output.getvalue()
    assert "local backend; isolation not established" in rendered
    assert "External input surfaces enabled: telegram, webhook" in rendered
    assert "SECURITY WARNING: untrusted input can reach unsandboxed local execution" in rendered
    assert "whole-process OS isolation" in rendered
    assert "allow-lists and approval prompts" in rendered.lower()
    assert "not a sandbox" in rendered.lower()


def test_marcel_static_checks_report_nonlocal_posture_without_sandbox_warning(monkeypatch, tmp_path):
    config = _marcel_config()
    config["terminal"] = {"backend": "docker"}
    config["platforms"] = {"telegram": {"enabled": True}}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (tmp_path / "MARCEL_WELCOME.md").write_text("Welcome", encoding="utf-8")
    monkeypatch.setenv("MARCEL_ROUTER_API_KEY", "present")

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_marcel_static_checks(tmp_path)

    rendered = output.getvalue()
    assert "docker whole-process isolation" in rendered
    assert "External input surfaces enabled: telegram" in rendered
    assert "SECURITY WARNING" not in rendered


def test_marcel_static_checks_do_not_treat_ssh_or_unknown_as_isolated(monkeypatch, tmp_path):
    for backend in ("ssh", "mystery"):
        config = _marcel_config()
        config["terminal"] = {"backend": backend}
        config["platforms"] = {"telegram": {"enabled": True}}
        (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        (tmp_path / "MARCEL_WELCOME.md").write_text("Welcome", encoding="utf-8")
        monkeypatch.setenv("MARCEL_ROUTER_API_KEY", "present")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_marcel_static_checks(tmp_path)

        rendered = output.getvalue()
        assert "isolation not established" in rendered
        assert "SECURITY WARNING" in rendered


def test_marcel_static_checks_detect_whatsapp_from_config_and_environment(monkeypatch, tmp_path):
    config = _marcel_config()
    config["terminal"] = {"backend": "local"}
    config["platforms"] = {"whatsapp": {"enabled": True}}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (tmp_path / "MARCEL_WELCOME.md").write_text("Welcome", encoding="utf-8")
    monkeypatch.setenv("MARCEL_ROUTER_API_KEY", "present")
    monkeypatch.setenv("WHATSAPP_ENABLED", "true")

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        run_marcel_static_checks(tmp_path)

    assert "External input surfaces enabled: whatsapp" in output.getvalue()