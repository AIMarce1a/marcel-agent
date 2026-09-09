import json

from tools import image_generation_tool as image_tool


class _Provider:
    name = "test-provider"

    def generate(self, **kwargs):
        return {
            "success": True,
            "image": "/tmp/result.png",
            "provider": "openai",
            "model": kwargs.get("model"),
        }


def test_per_call_provider_and_model_override_do_not_use_default(monkeypatch):
    requested = []

    def get_provider(name, force=False):
        requested.append((name, force))
        return _Provider()

    monkeypatch.setattr(image_tool, "_get_plugin_provider", get_provider)
    result = json.loads(image_tool._dispatch_to_plugin_provider(
        "portrait", "square", provider_name="openai", model="gpt-image-2-high"))

    assert requested == [("openai", False)]
    assert result["success"] is True
    assert result["model"] == "gpt-image-2-high"


def test_auto_provider_keeps_configured_default(monkeypatch):
    monkeypatch.setattr(image_tool, "_plugin_provider_name", lambda: "xai")
    monkeypatch.setattr(image_tool, "_get_plugin_provider", lambda name, force=False: _Provider())

    result = json.loads(image_tool._dispatch_to_plugin_provider(
        "portrait", "square", provider_name="auto"))

    assert result["success"] is True