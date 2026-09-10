"""Focused contracts for the pre-tag release qualification paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_installers_retain_anonymous_fresh_clone_and_pinned_commit_paths():
    shell = (REPO_ROOT / "scripts/install.sh").read_text()
    powershell = (REPO_ROOT / "scripts/install.ps1").read_text()

    for installer in (shell, powershell):
        assert "fresh install/archive download is disabled" not in installer
        assert "AdMind-ai/marcel-agent.git" in installer
        assert "Commit" in installer
    assert 'git clone --depth 1 --branch "$BRANCH"' in shell
    assert "git clone --depth 1 --branch $Branch" in powershell
    assert '--commit expects a hex SHA' in shell
    assert 'git checkout --detach "$INSTALL_COMMIT"' in shell
    assert 'git ... checkout --detach $Commit' not in powershell
    assert 'checkout --detach $Commit' in powershell
    assert "private repo" not in shell.lower()
    assert "private repo" not in powershell.lower()


def test_release_tag_picker_uses_semver_precedence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "test"],
        check=True,
    )
    (repo / "file").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "file"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
    tags = ["v0.21.0-rc.1", "v0.21.0", "v2026.4.13", "v2026.4.8", "v0.21.0-rc.2"]
    for tag in tags:
        subprocess.run(["git", "-C", str(repo), "tag", tag], check=True)

    script = REPO_ROOT / "scripts/sandbox/pick-release-tags.sh"
    result = subprocess.run(
        [str(script), "--repo", str(repo), "--count", "5"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == (
        '["v0.21.0-rc.1","v0.21.0-rc.2","v0.21.0",'
        '"v2026.4.8","v2026.4.13"]'
    )