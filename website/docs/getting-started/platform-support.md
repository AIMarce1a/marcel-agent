---
sidebar_position: 2.5
title: "Platform Support"
description: "Which operating systems, distribution methods, and features Marcel Agent supports."
---

# Platform Support

This is the support contract for the **0.21.0 prerelease**. A platform is
supported when a clean install, startup, and `marcel doctor` check are part of
the release qualification. Other combinations may work, but are not a promise
made by this prerelease.

---

## Supported for this prerelease

| Operating system | Architectures | Supported install | Qualification and limits |
| --- | --- | --- | --- |
| macOS 13+ | Apple Silicon (arm64) | [`install.sh`](./installation.md#macos) | CLI/runtime support. Intel macOS is not in this release's support set. |
| Ubuntu 22.04/24.04 LTS | x86_64 | [`install.sh`](./installation.md#linux) | Primary Linux target; suitable for desktop or a headless server. |
| Debian 12 | x86_64 | [`install.sh`](./installation.md) | Supported server target; use the dedicated service-user instructions. |
| Windows 10/11 | x86_64 | [`install.ps1`](./installation.md#windows) | Native CLI install. Desktop and platform-specific integrations may have additional limits. |
| Windows 10/11 with WSL2 (Ubuntu) | x86_64 | Linux [`install.sh`](./installation.md#linux) | Treat as Linux; Windows-native paths and services are not interchangeable with WSL paths. |

The supported matrix covers the core CLI and runtime. Provider availability,
browser dependencies, messaging adapters, and GPU acceleration can impose
additional requirements; see the feature-specific guide before depending on
one of those integrations.

---

## Best effort (not release-qualified)

These platforms are maintained in-tree only as a best effort.
Releases may break them, and we can't promise we'll fix them promptly when they break.

PRs will be accepted to fix issues with them, but they will take precedence below fixing issues with Tier 1 platforms.

| OS / Architecture              | Installation methods                                                 | Notes                                                                        |
| ------------------------------ | -------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Linux other than Ubuntu/Debian** | [`install.sh`](./installation.md#linux) | May work when the required glibc, Git, curl, and shell tooling are available; not tested for this prerelease. |
| **macOS Intel** | [`install.sh`](./installation.md#macos) | May work, but no release qualification or support commitment. |
| **Android/Termux** | [`install.sh`](./installation.md#linux) | Not release-qualified; mobile resource and native dependency limits apply. |
| **Nix/NixOS, Docker, ARM Linux** | Platform-specific methods | No prerelease qualification; report issues with the exact image/system details. |

## Unsupported

These platforms and distribution methods are **not** supported.
We suggest that you migrate to a supported distribution method or platform.
They may be broken right now, they may break more in the future.
PRs to fix them will _not_ be accepted, and any code that keeps compatibility with them may be removed at any point.

- installs via the AUR, Homebrew, or PyPI (`pip install` / `uv tool install`)
- unsupported Python or operating-system combinations
- running the Windows installer inside WSL (use the Linux installer there)

If you are using an unsupported distribution method, please read the [the installation guide](./installation.md) to learn how to switch to a supported one.
