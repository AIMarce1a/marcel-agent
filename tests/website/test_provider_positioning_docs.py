"""Contract checks for public provider and authentication positioning."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DOCS = (
    "website/docs/user-guide/features/web-dashboard.md",
    "website/docs/developer-guide/provider-runtime.md",
    "website/docs/getting-started/quickstart.md",
    "website/docs/getting-started/installation.md",
    "website/docs/integrations/index.md",
    "website/docs/integrations/providers.md",
    "website/docs/user-guide/features/api-server.md",
    "website/docs/user-guide/configuring-models.md",
)


def _public_docs() -> str:
    return "\n".join((REPO_ROOT / path).read_text(encoding="utf-8") for path in PUBLIC_DOCS)


def test_nous_is_not_positioned_as_marcel_default_or_required_path() -> None:
    docs = _public_docs().lower()
    forbidden_framing = (
        "recommended way to run marcel",
        "fastest path: nous portal",
        "easiest path: nous portal",
        "recommended fast path",
        "the recommended provider is **oauth (nous portal)",
        "the nous provider is the one suitable",
        "if you only have time to set up one integration",
    )
    for phrase in forbidden_framing:
        assert phrase not in docs, f"forbidden core-provider framing remains: {phrase}"


def test_public_docs_keep_optional_nous_compatibility_anchors() -> None:
    dashboard = (REPO_ROOT / "website/docs/user-guide/features/web-dashboard.md").read_text(
        encoding="utf-8"
    )
    providers = (REPO_ROOT / "website/docs/integrations/providers.md").read_text(
        encoding="utf-8"
    )
    assert "Nous Portal" in dashboard
    assert "#nous-research-oauth-provider" in dashboard
    assert "marcel setup --portal" in dashboard
    assert "### Nous Portal" in providers
    assert "marcel setup --portal" in providers