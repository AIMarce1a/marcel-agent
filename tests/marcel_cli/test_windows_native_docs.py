from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    # The launchers live in the managed binary dir OUTSIDE the git checkout
    # (MARCEL_HOME\bin, next to the managed uv) — NOT the whole venv\Scripts
    # (which would shadow the user's python, #83797) and NOT a dir inside
    # the checkout (which `marcel update`'s autostash swept off disk).
    assert "%LOCALAPPDATA%\\marcel\\bin" in doc
    assert (
        "Get-Command marcel        # should print "
        "C:\\Users\\<you>\\AppData\\Local\\marcel\\bin\\marcel.exe"
    ) in doc
    # Installer exposes $MarcelHome\bin, and must copy the launchers into it.
    assert '$marcelBin = "$MarcelHome\\bin"' in install
    assert "marcel.exe" in install and "marcel-acp.exe" in install
    # Guard against regressions to either legacy layout.
    assert '$marcelBin = "$InstallDir\\venv\\Scripts"' not in install
    assert '$marcelBin = "$InstallDir\\bin"' not in install
