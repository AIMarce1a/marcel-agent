"""Focused checks for the published Marcel Router contract and documentation."""

from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SPEC_PATH = ROOT / "docs" / "marcel-router-openapi.yaml"


def _operations(spec):
    return {
        (path, method)
        for path, definition in spec["paths"].items()
        for method in definition
        if method in {"get", "post", "delete", "put", "patch"}
    }


def test_openapi_contract_has_current_production_operations():
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    operations = _operations(spec)

    expected = {
        ("/v1/models", "get"),
        ("/v1/chat/completions", "post"),
        ("/v1/images/generations", "post"),
        ("/v1/realtime/sessions", "post"),
        ("/v1/realtime/connect", "get"),
        ("/v1/videos", "post"),
        ("/v1/videos/{id}", "get"),
        ("/v1/videos/{id}", "delete"),
        ("/v1/videos/{id}/content", "get"),
        ("/v1/embeddings", "post"),
        ("/v1/moderations", "post"),
        ("/v1/rerank", "post"),
        ("/v1/translate", "post"),
        ("/v1/documents/translations", "post"),
        ("/v1/documents/translations/{id}", "get"),
        ("/v1/documents/translations/{id}/content", "get"),
        ("/v1/tools", "get"),
        ("/v1/tools/search", "post"),
    }
    assert expected <= operations


def test_openapi_contract_does_not_publish_superseded_generic_job_routes():
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    assert "/v1/videos/generations" not in spec["paths"]
    assert "/v1/jobs/{job_id}" not in spec["paths"]


def test_docs_describe_media_and_realtime_as_available_capabilities():
    docs = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/marcel-router.md")
    ).lower()
    for phrase in ("planned", "reserved media", "reserved contract", "not implemented"):
        assert phrase not in docs
    for path in (
        "/v1/images/generations",
        "/v1/realtime/sessions",
        "/v1/realtime/connect",
        "/v1/videos",
    ):
        assert path in docs