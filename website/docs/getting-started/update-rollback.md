---
sidebar_position: 2.6
title: "Update and rollback"
description: "Safely update or restore a Marcel Agent prerelease installation."
---

# Update and rollback

These instructions apply to the supported installer layouts for the 0.21.0
prerelease. Do not update while a gateway or other Marcel process is writing
the same profile.

## Before updating

1. Record `marcel --version`, `marcel doctor`, and the installation method.
2. Back up `MARCEL_HOME` (normally `~/.marcel`). A backup must include the
   configuration, session database, memory, and credentials managed by the
   deployment.
3. Keep the previous release tag or archive available. The prerelease tag is
   `v0.21.0-rc.1`; verify its checksum before using an archive.

## Update

For an installation made by `install.sh` or `install.ps1`, use the built-in
update command:

```bash
marcel update
marcel doctor
marcel --version
```

On Windows, run the same commands in PowerShell. On a Linux server, run them
as the service user, stop the service first, and start it again only after
`marcel doctor` succeeds. A Docker or other image-based deployment updates by
replacing the image, not by running `marcel update`.

## Roll back

Stop Marcel, preserve the failed installation for diagnosis, and restore the
backup of `MARCEL_HOME` if the update changed configuration or data:

```bash
marcel gateway stop  # if a gateway is installed
cp -a ~/.marcel ~/.marcel.failed-update
```

Then restore the prior installer/archive for the recorded release and run
`marcel doctor`. Do not mix a newer data directory with an older runtime:
restore the data backup made before the update, or follow any migration
instructions for that release. Re-enable the service only after a successful
foreground smoke test.

Report the old and new versions, OS/architecture, install method, doctor
output, and the checksum of the artifact used. Never include API keys or
credential files in a report.

## Maintainer release checksum workflow

Build or collect the exact files that will be attached to the GitHub release,
then run the repository script from a clean checkout:

```bash
python scripts/release-checksums.py \
  --version 0.21.0 --tag v0.21.0-rc.1 \
  --output SHA256SUMS \
  dist/*
```

The script reads files only, hashes them in binary mode, sorts entries by
filename, and writes a portable two-column SHA-256 manifest. Review
`SHA256SUMS` and attach it beside the unchanged artifacts. Verify an artifact
with `sha256sum -c SHA256SUMS` on Linux or
`(Get-FileHash .\artifact.zip -Algorithm SHA256).Hash` on PowerShell. Run this
step after the release artifact is final and before publishing; it does not
create a tag or a GitHub release.