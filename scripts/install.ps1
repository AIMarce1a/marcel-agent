       } catch {
                    if ($prevEAP) { $ErrorActionPreference = $prevEAP }
                    Write-Warn "Playwright Chromium install could not be launched: $_"
                    Write-Info "Run manually later: cd `"$InstallDir`"; npx playwright install chromium"
                } finally {
                    Pop-Location
                }
            }
        }
    }

    # TUI
    $tuiDir = "$InstallDir\ui-tui"
    if (Test-Path "$tuiDir\package.json") {
        Write-Info "Installing TUI dependencies..."
        $tuiLog = "$env:TEMP\marcel-npm-tui-$(Get-Random).log"
        [void](_Run-NpmInstall "TUI" $tuiDir $tuiLog $npmExe)
    }

    Install-BrowserUseCli
    Install-CuaDriver
}

# The Browser Use CLI is the default browser backend when it is runnable
# (tools/browser_use_cli.py). Provision it at install time so fresh installs
# don't silently fall back to the built-in browser tools. Best-effort: any
# failure is non-fatal (browser_exec can still run via uvx, and `marcel tools`
# can install it later).
function Install-BrowserUseCli {
    if (-not $script:UvCmd) { Resolve-UvCmd }
    if (-not $script:UvCmd) {
        Write-Info "Skipping Browser Use CLI install (uv unavailable)"
        return
    }
    $managedBin = Join-Path $MarcelHome "bin"
    $managedBu = Join-Path $managedBin "browser-use.exe"
    # MANAGED-FIRST: only Marcel' managed copy short-circuits. A browser-use
    # on the user's PATH is a side install -- resolution prefers the managed
    # copy, so it must be provisioned regardless.
    if (Test-Path $managedBu) {
        Write-Success "Browser Use CLI already installed"
        return
    }

    Write-Info "Installing Browser Use CLI (default browser backend)..."
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # UV_TOOL_BIN_DIR keeps the binary inside Marcel' managed bin dir,
        # where the browser tool resolves it -- no reliance on the user PATH.
        $env:UV_TOOL_BIN_DIR = $managedBin
        $env:UV_NO_CONFIG = "1"
        & $script:UvCmd tool install browser-use 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Browser Use CLI installed"
        } else {
            Write-Warn "Browser Use CLI install failed (exit $LASTEXITCODE) -- browser automation falls back to built-in tools."
            Write-Info "Install later with: uv tool install browser-use  (or via 'marcel tools')"
        }
    } catch {
        Write-Warn "Browser Use CLI install failed: $_"
    } finally {
        $ErrorActionPreference = $prevEAP
        Remove-Item Env:\UV_TOOL_BIN_DIR -ErrorAction SilentlyContinue
        Remove-Item Env:\UV_NO_CONFIG -ErrorAction SilentlyContinue
    }
}

function Test-CuaDriverRuntimeContract {
    param([Parameter(Mandatory = $true)][string]$DriverPath)

    try {
        $versionOutput = (& $DriverPath --version 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        $versionMatch = [regex]::Match($versionOutput, '(\d+\.\d+\.\d+)')
        if (-not $versionMatch.Success) {
            return $false
        }
        if ([version]($versionMatch.Groups[1].Value) -lt [version]'0.20.0') {
            return $false
        }

        $manifestOutput = (& $DriverPath manifest 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $manifestOutput) {
            return $false
        }
        $manifest = $manifestOutput | ConvertFrom-Json
        if (-not $manifest.mcp_invocation.args) {
            return $false
        }

        $required = @{
            mcp = @('--socket', '--grant')
            serve = @(
                '--socket', '--permission-mode', '--capability-manifest',
                '--approve-capability-manifest', '--embedded'
            )
            stop = @('--socket')
        }
        foreach ($commandName in $required.Keys) {
            $command = $manifest.subcommands | Where-Object { $_.name -eq $commandName }
            if (-not $command) {
                return $false
            }
            $argNames = @($command.args | ForEach-Object { $_.name })
            foreach ($requiredArg in $required[$commandName]) {
                if ($requiredArg -notin $argNames) {
                    return $false
                }
            }
        }
        return $true
    } catch {
        return $false
    }
}

# cua-driver powers the computer_use toolset (background desktop control).
# Provision it at install time so enabling the tool later -- via `marcel
# tools`, the dashboard, or the desktop app -- is a config flip, not a
# surprise multi-minute binary fetch. Best-effort and non-fatal: the enable
# paths still lazy-install via install_cua_driver() (marcel_cli/tools_config)
# when this step was skipped or failed.
function Install-CuaDriver {
    if ($SkipComputerUse) {
        Write-Info "Skipping Computer Use (cua-driver) install (-SkipComputerUse)"
        return
    }
    $existingCuaDriver = Get-Command cua-driver -ErrorAction SilentlyContinue
    if ($existingCuaDriver) {
        if (Test-CuaDriverRuntimeContract -DriverPath $existingCuaDriver.Source) {
            Write-Success "Computer Use driver (cua-driver) already installed and compatible"
            return
        }
        Write-Warn "Existing cua-driver is old or incomplete; repairing it"
    }

    Write-Info "Installing Computer Use driver (cua-driver)..."
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Same upstream installer `marcel computer-use install` runs. Bounded
        # via a background job: the upstream installer serializes with its own
        # lock (600s stale window), so the ceiling sits above that -- matching
        # Marcel' _CUA_INSTALLER_TIMEOUT (660s).
        $job = Start-Job -ScriptBlock {
            Invoke-RestMethod -UseBasicParsing "https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1" | Invoke-Expression
        }
        if (Wait-Job $job -Timeout 660) {
            Receive-Job $job -ErrorAction SilentlyContinue | Out-Null
            Remove-Job $job -Force -ErrorAction SilentlyContinue
            $installedCuaDriver = Get-Command cua-driver -ErrorAction SilentlyContinue
            if ($installedCuaDriver -and (Test-CuaDriverRuntimeContract -DriverPath $installedCuaDriver.Source)) {
                Write-Success "Computer Use driver installed (enable via 'marcel tools' -> Computer Use)"
            } else {
                Write-Warn "Computer Use driver install did not produce a compatible runtime -- repair it before enabling the tool."
                Write-Info "Install later with: marcel computer-use install"
            }
        } else {
            Stop-Job $job -ErrorAction SilentlyContinue
            Remove-Job $job -Force -ErrorAction SilentlyContinue
            Write-Warn "Computer Use driver install timed out -- it will install on demand when you enable the tool."
            Write-Info "Install later with: marcel computer-use install"
        }
    } catch {
        Write-Warn "Computer Use driver install failed: $_"
        Write-Info "Install later with: marcel computer-use install"
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

# Clear the cached Electron download + any half-written unpacked output so the
# next `npm run pack` re-downloads and re-stages from scratch. A corrupt zip in
# the per-user Electron download cache - most often a partial download resumed
# into the same file, leaving concatenated junk - makes electron-builder's
# `app-builder unpack-electron` extract a tree MISSING the electron binary, so
# the final `electron` -> `Marcel` rename dies with ENOENT and every re-run
# repeats the broken extraction forever.
#
# We deliberately do not validate the zip ourselves: the common
# prepended/concatenated-junk corruption slips past naive checks, so a
# self-rolled gate would skip the real-world case. We unconditionally drop the
# cached electron-*.zip (loose copy and any @electron/get hash-subdir copy) plus
# the stale unpacked dir, then let the caller retry once - @electron/get
# re-downloads with its own SHASUM verification, the real source of truth.
#
# Returns the removed paths. Best-effort: never throws.
function Clear-ElectronBuildCache {
    param([string]$DesktopDir)
    $removed = @()

    # Per-user Electron download cache dirs, honoring the overrides @electron/get
    # respects, then the Windows default (%LOCALAPPDATA%\electron\Cache).
    $cacheDirs = @()
    if ($env:electron_config_cache) { $cacheDirs += $env:electron_config_cache }
    if ($env:ELECTRON_CACHE)        { $cacheDirs += $env:ELECTRON_CACHE }
    if ($env:LOCALAPPDATA)          { $cacheDirs += (Join-Path $env:LOCALAPPDATA 'electron\Cache') }
    $cacheDirs += (Join-Path $HOME 'AppData\Local\electron\Cache')

    foreach ($dir in $cacheDirs) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        # Recurse: the bad copy may be the top-level zip OR a copy inside an
        # @electron/get hash subdir.
        $removed += @(Get-ChildItem -LiteralPath $dir -Recurse -Filter 'electron-*.zip' -File -ErrorAction SilentlyContinue | ForEach-Object {
            try { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop; $_.FullName } catch { }
        })
    }

    # A half-written unpacked dir from an interrupted prior pack poisons the
    # rename even after the zip is fixed (win-unpacked / win-arm64-unpacked).
    $releaseDir = Join-Path $DesktopDir 'release'
    if (Test-Path -LiteralPath $releaseDir) {
        $removed += @(Get-ChildItem -LiteralPath $releaseDir -Directory -Filter '*-unpacked' -ErrorAction SilentlyContinue | ForEach-Object {
            try { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop; $_.FullName } catch { }
        })
    }

    return $removed
}

# Last-resort Electron mirror after GitHub download fails (#47266).
$script:DesktopElectronFallbackMirror = "https://npmmirror.com/mirrors/electron/"

# Electron package dir -- workspace-local nest first, then root hoist.
function Get-ElectronDir {
    param([string]$InstallDir)
    $desktopLocal = Join-Path $InstallDir 'apps\desktop\node_modules\electron'
    if (Test-Path -LiteralPath $desktopLocal) { return $desktopLocal }
    return (Join-Path $InstallDir 'node_modules\electron')
}

# True when dist/ holds a usable Electron binary (#38673 / run-electron-builder.mjs).
function Test-ElectronDist {
    param([string]$InstallDir)
    $electronDir = Get-ElectronDir -InstallDir $InstallDir
    $distExe = Join-Path $electronDir 'dist\electron.exe'
    return (Test-Path -LiteralPath $distExe)
}

# Best-effort: run electron/install.js to populate dist/ (optional mirror).
function Restore-ElectronDist {
    param([string]$InstallDir, [string]$Mirror)
    if (Test-ElectronDist -InstallDir $InstallDir) { return $true }

    $electronDir = Get-ElectronDir -InstallDir $InstallDir
    $distExe = Join-Path $electronDir 'dist\electron.exe'
    $installer = Join-Path $electronDir 'install.js'
    if (-not (Test-Path -LiteralPath $installer)) { return $false }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { return $false }

    $distDir = Join-Path $electronDir 'dist'
    if (Test-Path -LiteralPath $distDir) {
        Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath (Join-Path $electronDir 'path.txt') -Force -ErrorAction SilentlyContinue

    $prevMirror = $env:ELECTRON_MIRROR
    if ($Mirror) { $env:ELECTRON_MIRROR = $Mirror }
    try {
        # Out-Host so the downloader's progress shows on the console WITHOUT
        # leaking into this function's return value (PowerShell returns every
        # object left on the output stream, so a bare pipe here would make the
        # boolean below ambiguous).
        & $node.Source $installer 2>&1 | ForEach-Object { "$_" } | Out-Host
    } catch {
    } finally {
        $env:ELECTRON_MIRROR = $prevMirror
    }
    return (Test-Path -LiteralPath $distExe)
}

function Test-ElectronPkgStagedMissingDist {
    param([string]$InstallDir)
    $electronDir = Get-ElectronDir -InstallDir $InstallDir
    return (
        (Test-Path -LiteralPath (Join-Path $electronDir 'package.json')) -and
        (Test-Path -LiteralPath (Join-Path $electronDir 'install.js')) -and
        (-not (Test-ElectronDist -InstallDir $InstallDir))
    )
}

function Try-RestoreElectronDist {
    param([string]$InstallDir)
    if (Restore-ElectronDist -InstallDir $InstallDir) { return $true }
    if ($env:ELECTRON_MIRROR) { return $false }
    return Restore-ElectronDist -InstallDir $InstallDir -Mirror $script:DesktopElectronFallbackMirror
}

function Install-DesktopVoiceDeps {
    # Desktop ships with working voice out of the box: eagerly install the
    # wake-word + local-STT stacks ([wake] + [voice] extras) instead of
    # leaving them to lazy first-use install. Policy change (Teknium, July
    # 2026, #70509 testing): the first ear-click used to trigger a
    # multi-minute onnxruntime pip install that froze the UI and blew RPC
    # timeouts. Best-effort -- lazy install remains the fallback for anything
    # this step fails to fetch.
    if (-not $script:UvCmd) { Resolve-UvCmd }
    if (-not $script:UvCmd) {
        Write-Warn "uv unavailable -- voice/wake deps will lazy-install at first use instead"
        return
    }
    $env:VIRTUAL_ENV = "$InstallDir\venv"
    Write-Info "Installing voice + wake-word dependencies (onnxruntime, faster-whisper -- 1-3min)..."
    Push-Location $InstallDir
    try {
        Invoke-NativeWithRelaxedErrorAction { & $UvCmd pip install -e ".[wake,voice]" }
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Voice + wake-word dependencies installed"
        } else {
            Write-Warn "Voice/wake dependency install failed (exit $LASTEXITCODE) -- they will lazy-install at first use"
        }
    } finally {
        Pop-Location
    }
}

function Install-Desktop {
    # Build apps/desktop into a launchable Marcel.exe. Only called from
    # Stage-Desktop, which is itself only included in the manifest when
    # -IncludeDesktop was passed to install.ps1.
    #
    # The workspace npm install at repo root (done by Install-NodeDeps for
    # browser tools) does NOT pull apps/desktop's dependencies, because the
    # browser-tools workspace at $InstallDir\package.json is a separate
    # workspace from apps/*. We do a full root-level `npm install` here
    # so the workspace resolves apps/desktop's deps (including Electron
    # itself, ~150MB), then run `npm run pack` in apps/desktop which
    # produces the unpacked binary at apps/desktop/release/<os>-unpacked/.
    #
    # The Tauri bootstrap installer's launch_marcel_desktop command
    # resolves apps/desktop/release/win-unpacked/Marcel.exe directly,
    # so an "unpacked" build (electron-builder --dir) is enough -- we
    # don't need to produce an NSIS/MSI artifact here.

    # Always re-resolve Node here. Stages run in separate PowerShell processes,
    # so $script:HasNode from Stage-Node isn't visible; more importantly Test-Node
    # enforces the supported Node lines and prepends the Marcel-managed Node to
    # PATH, so the build never runs on an unsupported system Node -- the cause
    # of the opaque "Build desktop app ... exit code 1" failure (Vite crashes on
    # old Node).
    Test-Node | Out-Null
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Warn "Skipping desktop build (Node.js / npm not on PATH)"
        $script:_StageSkippedReason = "Node.js not available"
        return
    }

    $desktopDir = "$InstallDir\apps\desktop"
    if (-not (Test-Path "$desktopDir\package.json")) {
        Write-Warn "Skipping desktop build (apps/desktop not present in checkout)"
        $script:_StageSkippedReason = "apps/desktop not present"
        return
    }

    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCmd) {
        Write-Warn "Skipping desktop build (npm not on PATH)"
        $script:_StageSkippedReason = "npm not found"
        return
    }
    $npmExe = $npmCmd.Source
    if ($npmExe -like "*.ps1") {
        $sibling = Join-Path (Split-Path $npmExe -Parent) "npm.cmd"
        if (Test-Path $sibling) { $npmExe = $sibling }
    }

    # 1. Workspace-level install so apps/desktop's deps (Electron, Vite,
    # node-pty prebuilds, etc.) actually land in node_modules. This is
    # the SAME `npm install` Install-NodeDeps does for browser tools,
    # but at the root rather than the browser-tools workspace, so all
    # apps/* workspaces resolve.
    Write-Info "Installing desktop workspace dependencies (this includes Electron ~150MB, takes 1-3min)..."
    Push-Location $InstallDir
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        # Drop --silent so npm emits its full progress + error trail.
        # When this fails on a non-dev box (e.g. native-module build
        # without VS Build Tools, ETARGET on a transitive, etc.), the
        # actual reason needs to reach the Tauri installer's log; with
        # --silent it was completely suppressed and the user just saw
        # "exit 1" with no actionable detail.
        #
        # The streaming sink in bootstrap.rs's run_install_script
        # captures every stdout/stderr line as it's emitted, so we don't
        # need a side TEMP log file -- the installer's bootstrap log
        # IS the artifact a support engineer reads.
        #
        # Prefer `npm ci`: it wipes node_modules and reinstalls from the
        # lockfile, always producing a complete tree. Bare `npm install`
        # can report "up to date" against a stale
        # node_modules\.package-lock.json marker while node_modules is
        # actually empty (Windows workspace-hoisting flake), leaving
        # tsc/typescript unresolved so `npm run pack`'s `tsc -b` dies with
        # no obvious cause. Fall back to `npm install` only if `npm ci`
        # fails (lockfile out of sync / very old npm without ci).
        #
        # Tee the merged output into $npmOut while still emitting every line
        # live. We don't need a side log file (the bootstrap streaming sink
        # is the artifact), but on failure we scan $npmOut for the TLS-trust
        # signature so corporate-proxy users get the NODE_EXTRA_CA_CERTS hint
        # instead of an opaque "exit 1" (issue #38016).
        & $npmExe ci 2>&1 | ForEach-Object { "$_" } | Tee-Object -Variable npmOut
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            Write-Info "  npm ci failed (exit $code) -- retrying with npm install..."
            & $npmExe install 2>&1 | ForEach-Object { "$_" } | Tee-Object -Variable npmOut
            $code = $LASTEXITCODE
        }
        $ErrorActionPreference = $prevEAP
        if ($code -ne 0) {
            if (Test-ElectronPkgStagedMissingDist -InstallDir $InstallDir) {
                Write-Warn "Desktop dependency install failed with a missing Electron dist; attempting self-heal..."
                Try-RestoreElectronDist -InstallDir $InstallDir | Out-Null
            } else {
                Show-NpmCertHint ($npmOut -join "`n") | Out-Null
                # Replay npm's own debug log into our stream: the terse
                # summary above rarely contains the postinstall stderr
                # (e.g. Electron's install.js) that explains the failure.
                Write-NpmDebugLogTail -NpmOutput ($npmOut -join "`n")
                throw "desktop workspace npm install failed (exit $code) -- see lines above for cause"
            }
        } else {
            Write-Success "Desktop workspace dependencies installed"
        }
    } catch {
        if ($prevEAP) { $ErrorActionPreference = $prevEAP }
        Pop-Location
        throw
    }
    Pop-Location

    # 2. Build apps/desktop. `npm run pack` runs:
    #      assert-root-install + write-build-stamp + stage-native-deps +
    #      tsc -b + vite build + electron-builder --dir
    # The --dir mode produces an unpacked Marcel.exe in
    # apps/desktop/release/win-unpacked/ without bundling NSIS/MSI;
    # we don't need a distributable installer artifact, just a
    # launchable binary the Tauri installer can spawn.
    #
    # CSC_IDENTITY_AUTO_DISCOVERY=false tells electron-builder we are
    # NOT signing the output. Combined with signAndEditExecutable=false in
    # apps/desktop/package.json's build.win block, electron-builder never
    # invokes signtool and therefore never fetches/extracts winCodeSign
    # (whose macOS symlinks crash 7-Zip on non-admin Windows -- a dead end we
    # are NOT trying to work around). The Marcel icon + product name are
    # stamped onto Marcel.exe by our own rcedit step (Set-DesktopExeIdentity)
    # AFTER this build, completely decoupled from electron-builder signing.
    #
    # WIN_CSC_LINK and WIN_CSC_KEY_PASSWORD explicitly cleared as
    # belt-and-suspenders: if the user's environment has them set
    # for some other tool, electron-builder would still try to sign.
    Write-Info "Building desktop app (this takes 1-3 minutes)..."
    $buildLog = "$env:TEMP\marcel-desktop-build-$(Get-Random).log"
    # Seed GITHUB_SHA for write-build-stamp.mjs. The stamp prefers CI env vars
    # over `git rev-parse`, so this covers: (1) node can't find git.exe on PATH
    # even though this PowerShell session can, (2) ZIP/init trees that still
    # lack a HEAD after a failed post-extract fetch. Without it the desktop
    # pack dies with "could not determine git commit" (#50823).
    if (-not $env:GITHUB_SHA) {
        if ($Commit) {
            $env:GITHUB_SHA = $Commit
        } else {
            Push-Location $InstallDir
            try {
                $global:LASTEXITCODE = 0
                $resolvedSha = & git -c windows.appendAtomically=false rev-parse HEAD 2>$null
                if ($LASTEXITCODE -ne 0 -or -not $resolvedSha) {
                    # ZIP path may have FETCH_HEAD after a fetch even when HEAD is unset.
                    $global:LASTEXITCODE = 0
                    $resolvedSha = & git -c windows.appendAtomically=false rev-parse FETCH_HEAD 2>$null
                }
                if ($LASTEXITCODE -eq 0 -and $resolvedSha) {
                    $env:GITHUB_SHA = ("$resolvedSha").Trim()
                }
            } catch { } finally {
                Pop-Location
            }
        }
    }
    if (-not $env:GITHUB_REF_NAME) {
        $env:GITHUB_REF_NAME = if ($Branch) { $Branch } else { "main" }
    }
    if ($env:GITHUB_SHA) {
        $shaPreview = if ($env:GITHUB_SHA.Length -ge 12) { $env:GITHUB_SHA.Substring(0, 12) } else { $env:GITHUB_SHA }
        Write-Info "Desktop build stamp: $shaPreview ($($env:GITHUB_REF_NAME))"
    } else {
        Write-Warn "Could not resolve a git commit for the desktop stamp -- write-build-stamp will use its non-git fallback"
    }
    Push-Location $desktopDir
    $prevEAP = $ErrorActionPreference
    $prevCSCAuto = $env:CSC_IDENTITY_AUTO_DISCOVERY
    $prevWinCscLink = $env:WIN_CSC_LINK
    $prevWinCscKeyPassword = $env:WIN_CSC_KEY_PASSWORD
    try {
        $ErrorActionPreference = "Continue"
        $env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
        $env:WIN_CSC_LINK = ""
        $env:WIN_CSC_KEY_PASSWORD = ""
        & $npmExe run pack 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $buildLog
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            $purged = @()
            $restored = $false
            if (-not (Test-ElectronDist -InstallDir $InstallDir)) {
                $purged = @(Clear-ElectronBuildCache -DesktopDir $desktopDir)
                $restored = Restore-ElectronDist -InstallDir $InstallDir
            }
            if ($restored) {
                Write-Warn "Desktop build failed - refreshed the Electron download, retrying once:"
                foreach ($p in $purged) { Write-Info "  - $p" }
                & $npmExe run pack 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $buildLog
                $code = $LASTEXITCODE
            }
        }
        if ($code -ne 0 -and -not $env:ELECTRON_MIRROR) {
            $mirror = $script:DesktopElectronFallbackMirror
            Write-Warn "Desktop build still failing - the Electron download from GitHub looks blocked."
            Write-Warn "Re-downloading Electron via a public mirror ($mirror), then rebuilding:"
            Write-Info "  (set ELECTRON_MIRROR yourself to use a different/trusted mirror)"
            if (-not (Test-ElectronDist -InstallDir $InstallDir)) {
                Restore-ElectronDist -InstallDir $InstallDir -Mirror $mirror | Out-Null
            }
            $prevMirror = $env:ELECTRON_MIRROR
            $env:ELECTRON_MIRROR = $mirror
            try {
                & $npmExe run pack 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $buildLog
                $code = $LASTEXITCODE
            } finally {
                $env:ELECTRON_MIRROR = $prevMirror
            }
        }
        $ErrorActionPreference = $prevEAP
        if ($code -ne 0) {
            $errText = Get-Content $buildLog -Raw -ErrorAction SilentlyContinue
            if ($errText) {
                $snippet = if ($errText.Length -gt 1800) { $errText.Substring(0, 1800) + "..." } else { $errText }
                Write-Info "  desktop build output:"
                foreach ($line in $snippet -split "`n") { Write-Host "    $line" -ForegroundColor DarkGray }
                Write-Info "  Full log: $buildLog"
            }
            # `npm run pack` failures (lifecycle script exits) also land in
            # npm's debug log; replay it so the bootstrap log carries the
            # full evidence even when $buildLog's tail cuts off the cause.
            Write-NpmDebugLogTail -NpmOutput $errText
            throw "apps/desktop build failed (exit $code)"
        }
        Write-Success "Desktop app built"
        Remove-Item -LiteralPath $buildLog -Force -ErrorAction SilentlyContinue
    } catch {
        if ($prevEAP) { $ErrorActionPreference = $prevEAP }
        Pop-Location
        throw
    } finally {
        # Restore env to whatever the caller had -- don't leak our
        # signing-off override into anything install.ps1 invokes later
        # (Stage-PlatformSdks, etc.).
        $env:CSC_IDENTITY_AUTO_DISCOVERY = $prevCSCAuto
        $env:WIN_CSC_LINK = $prevWinCscLink
        $env:WIN_CSC_KEY_PASSWORD = $prevWinCscKeyPassword
    }
    Pop-Location

    # 3. Sanity-check the produced binary. Probe both arches so this works
    # on x64 and arm64 build machines.
    $exeCandidates = @(
        "$desktopDir\release\win-unpacked\Marcel.exe",
        "$desktopDir\release\win-arm64-unpacked\Marcel.exe"
    )
    $found = $false
    $desktopExe = $null
    foreach ($cand in $exeCandidates) {
        if (Test-Path $cand) {
            Write-Success "Desktop ready: $cand"
            $desktopExe = $cand
            $found = $true
            break
        }
    }
    if (-not $found) {
        throw "Desktop build completed but no Marcel.exe was found under $desktopDir\release\*-unpacked\"
    }

    # 3b. The Marcel icon + identity are stamped onto Marcel.exe by the
    #     electron-builder `afterPack` hook (apps/desktop/scripts/after-pack.mjs)
    #     during `npm run pack` above -- for every build, so the installer's
    #     --update rebuild stays branded too. No separate stamp step needed here.
    #     electron-builder's own rcedit step stays disabled (signAndEditExecutable
    #     =false) because enabling it drags in signtool -> winCodeSign -> the
    #     unfixable symlink crash; the afterPack hook runs rcedit directly.

    # 3c. Grant ALL APPLICATION PACKAGES (S-1-15-2-2) RX on the unpacked app
    #     directory. Chromium's GPU/renderer sandboxes CHECK-fail with
    #     0x80000003 when this ACE is missing alongside orphan AppContainer
    #     SIDs under %LOCALAPPDATA% (electron/electron#51761, marcel-agent#38216).
    #     Best-effort -- never fail an otherwise-good install over ACL repair.
    try {
        $appDir = Split-Path -Parent $desktopExe
        & icacls $appDir /grant "*S-1-15-2-2:(OI)(CI)(RX)" /T /C /Q | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Granted AppContainer read access on $appDir"
        } else {
            Write-Warn "icacls AppContainer grant returned exit $LASTEXITCODE for $appDir"
        }
    } catch {
        Write-Warn "Could not grant AppContainer ACL: $($_.Exception.Message)"
    }

    # 4. Create Start Menu + Desktop shortcuts pointing DIRECTLY at the packed
    #    Marcel.exe. We deliberately do NOT point them at `marcel desktop`: that
    #    command rebuilds (npm install + electron-builder) on every launch,
    #    which would cost minutes each time. The packed exe is the consumer --
    #    launching it directly is instant, and updates flow through the
    #    installer's --update path (which rebuilds once, then relaunches).
    New-DesktopShortcuts -TargetExe $desktopExe
}

function New-DesktopShortcuts {
    param([Parameter(Mandatory = $true)][string]$TargetExe)

    # Best-effort: a shortcut failure must never fail an otherwise-good install.
    try {
        $shell = New-Object -ComObject WScript.Shell
        $workDir = Split-Path -Parent $TargetExe

        # Prefer the standalone icon.ico (shipped beside the exe via
        # electron-builder extraResources -> resources/icon.ico) over the exe's
        # embedded resource. An explicit .ico path is more stable across update
        # cycles: pointing at "$TargetExe,0" makes Windows cache the icon it
        # extracted from the exe at shortcut-creation time, and that cached
        # bitmap can persist (showing the OLD/Electron icon) even after the exe
        # is re-stamped on update. A dedicated .ico sidesteps that extraction.
        $iconIco = Join-Path $workDir 'resources\icon.ico'
        if (Test-Path $iconIco) {
            $iconLocation = "$iconIco,0"
        } else {
            $iconLocation = "$TargetExe,0"
        }

        $targets = @(
            (Join-Path ([Environment]::GetFolderPath('Programs')) 'Marcel.lnk'),
            (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Marcel.lnk')
        )

        foreach ($lnkPath in $targets) {
            try {
                $parent = Split-Path -Parent $lnkPath
                if (-not (Test-Path $parent)) {
                    New-Item -ItemType Directory -Force -Path $parent | Out-Null
                }
                $sc = $shell.CreateShortcut($lnkPath)
                $sc.TargetPath = $TargetExe
                $sc.WorkingDirectory = $workDir
                $sc.IconLocation = $iconLocation
                $sc.Description = 'Marcel Agent'
                $sc.Save()
                Write-Success "Shortcut created: $lnkPath"
            } catch {
                Write-Warn "Could not create shortcut $lnkPath : $($_.Exception.Message)"
            }
        }

        # Bust the Windows shell icon cache so the desktop/Start-Menu shortcut
        # repaints with the (possibly newly-stamped) icon instead of a stale
        # cached bitmap. Critical on the --update path: the exe was re-stamped
        # with the Marcel icon, but without this the shortcut can keep drawing
        # the old Electron icon until the user manually refreshes / reboots.
        # Best-effort and silent -- never fail the install over a cosmetic cache.
        try {
            & ie4uinit.exe -show 2>$null
        } catch {
            # ie4uinit may be absent/renamed on some SKUs -- ignore.
        }
    } catch {
        Write-Warn "Skipping shortcut creation: $($_.Exception.Message)"
    }
}

function Install-PlatformSdks {
    # Ensure messaging-platform SDKs matching tokens the user added to
    # ~/.marcel/.env are importable.  Two problems this solves:
    #
    # 1. The tiered `uv pip install` cascade above can fall through to a
    #    lower tier when the first fails (common when RL git deps choke),
    #    which silently skips some messaging SDKs from [messaging].
    # 2. `uv` creates the venv without pip.  If a messaging SDK ends up
    #    missing, the user can't `pip install python-telegram-bot` to
    #    recover -- pip simply isn't in their venv.
    #
    # Strategy: bootstrap pip via `python -m ensurepip` (idempotent), then
    # for each token set in .env, verify the matching SDK imports.  If not,
    # run one targeted `pip install` as last-chance recovery.  Keeps fresh
    # Windows installs from hitting silent "python-telegram-bot not installed"
    # at runtime.
    if ($NoVenv) {
        Write-Info "Skipping platform-SDK verification (-NoVenv: no venv to bootstrap)"
        return
    }

    $pythonExe = "$InstallDir\venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        Write-Warn "Skipping platform-SDK verification: $pythonExe not found"
        return
    }

    $envPath = "$MarcelHome\.env"
    if (-not (Test-Path $envPath)) { return }
    $envLines = Get-Content $envPath -ErrorAction SilentlyContinue

    # Map: env var set in .env -> (import name, pip spec matching [messaging] extra).
    # Specs mirror pyproject.toml to avoid version drift.
    $sdkMap = @(
        @{ Var = "TELEGRAM_BOT_TOKEN"; Import = "telegram";  Spec = "python-telegram-bot[webhooks]>=22.6,<23" },
        @{ Var = "DISCORD_BOT_TOKEN";  Import = "discord";   Spec = "discord.py[voice]>=2.7.1,<3" },
        @{ Var = "SLACK_BOT_TOKEN";    Import = "slack_sdk"; Spec = "slack-sdk>=3.27.0,<4" },
        @{ Var = "SLACK_APP_TOKEN";    Import = "slack_bolt";Spec = "slack-bolt>=1.18.0,<2" },
        @{ Var = "WHATSAPP_ENABLED";   Import = "qrcode";    Spec = "qrcode>=7.0,<8" }
    )

    # Which tokens are actually set (not placeholder)?
    $needed = @()
    foreach ($sdk in $sdkMap) {
        $match = $envLines | Where-Object {
            $_ -match ("^" + [regex]::Escape($sdk.Var) + "=.+") `
            -and $_ -notmatch "your-token-here" `
            -and $_ -notmatch "^\s*#"
        }
        if ($match) { $needed += $sdk }
    }
    if ($needed.Count -eq 0) { return }

    Write-Host ""
    Write-Info "Verifying platform SDKs for tokens found in $envPath ..."

    # Verify each SDK's import without triggering side-effect imports.
    # Quirk: PowerShell wraps non-zero-exit native stderr as a
    # NativeCommandError that prints even with `2>$null` / `*> $null`
    # unless we set $ErrorActionPreference to SilentlyContinue for the
    # span.  Save + restore rather than nuking globally.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $missing = @()
        foreach ($sdk in $needed) {
            & $pythonExe -c "import $($sdk.Import)" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                $missing += $sdk
                Write-Warn "  $($sdk.Import) NOT importable (needed for $($sdk.Var))"
            } else {
                Write-Success "  $($sdk.Import) OK"
            }
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    if ($missing.Count -eq 0) { return }

    # Bootstrap pip into the venv if it isn't there.  `uv` creates venvs
    # without pip; ensurepip is the stdlib-blessed way to add it.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $pythonExe -m pip --version 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Info "Bootstrapping pip into venv (uv doesn't ship pip)..."
            & $pythonExe -m ensurepip --upgrade 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "ensurepip failed -- can't auto-install missing SDKs."
                Write-Info "Manual recovery: $UvCmd pip install `"$($missing[0].Spec)`""
                return
            }
        }

        foreach ($sdk in $missing) {
            Write-Info "  Installing $($sdk.Spec) ..."
            & $pythonExe -m pip install $sdk.Spec 2>&1 | ForEach-Object { Write-Host "    $_" }
            if ($LASTEXITCODE -eq 0) {
                Write-Success "  Installed $($sdk.Import)"
            } else {
                Write-Warn "  Failed to install $($sdk.Spec). Recover manually: $pythonExe -m pip install `"$($sdk.Spec)`""
            }
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function Invoke-SetupWizard {
    if ($SkipSetup) {
        Write-Info "Skipping setup wizard (-SkipSetup)"
        return
    }

    if ($NonInteractive) {
        # The setup wizard prompts for API keys, model choice, persona, etc.
        # Non-interactive callers (GUI installer) own that UX themselves; let
        # them drive it after install.ps1 returns.
        Write-Info "Skipping setup wizard (non-interactive). Configure via the GUI or 'marcel setup'."
        return
    }

    Write-Host ""
    Write-Info "Starting setup wizard..."
    Write-Host ""

    Push-Location $InstallDir

    # Run marcel setup using the venv Python directly (no activation needed)
    if (-not $NoVenv) {
        & ".\venv\Scripts\python.exe" -m marcel_cli.main setup
    } else {
        python -m marcel_cli.main setup
    }

    Pop-Location
}

function Start-GatewayIfConfigured {
    $envPath = "$MarcelHome\.env"
    if (-not (Test-Path $envPath)) { return }

    $hasMessaging = $false
    $content = Get-Content $envPath -ErrorAction SilentlyContinue
    foreach ($var in @("TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "WHATSAPP_ENABLED")) {
        $match = $content | Where-Object { $_ -match "^${var}=.+" -and $_ -notmatch "your-token-here" }
        if ($match) { $hasMessaging = $true; break }
    }

    if (-not $hasMessaging) { return }

    $marcelCmd = "$InstallDir\venv\Scripts\marcel.exe"
    if (-not (Test-Path $marcelCmd)) {
        $marcelCmd = "marcel"
    }

    # If WhatsApp is enabled but not yet paired, run foreground for QR scan
    $whatsappEnabled = $content | Where-Object { $_ -match "^WHATSAPP_ENABLED=true" }
    $whatsappSession = "$MarcelHome\whatsapp\session\creds.json"
    if ($whatsappEnabled -and -not (Test-Path $whatsappSession)) {
        Write-Host ""
        Write-Info "WhatsApp is enabled but not yet paired."
        Write-Info "Running 'marcel whatsapp' to pair via QR code..."
        Write-Host ""
        # Non-interactive callers (GUI installer, CI) skip the QR-pair prompt;
        # WhatsApp pairing requires a human looking at a phone camera, so the
        # downstream UI is responsible for surfacing this when it makes sense.
        if (-not $NonInteractive) {
            $response = Read-Host "Pair WhatsApp now? [Y/n]"
            if ($response -eq "" -or $response -match "^[Yy]") {
                try {
                    & $marcelCmd whatsapp
                } catch {
                    # Expected after pairing completes
                }
            }
        } else {
            Write-Info "Skipping WhatsApp pairing prompt (non-interactive)."
        }
    }

    Write-Host ""
    Write-Info "Messaging platform token detected!"
    Write-Info "The gateway handles messaging platforms and cron job execution."
    Write-Host ""

    # In non-interactive mode the gateway lifecycle is the caller's problem
    # (the GUI manages its own gateway process, CI doesn't want background
    # services on the build agent, etc.).  Treat it like the user declined.
    if ($NonInteractive) {
        Write-Info "Skipping gateway autostart prompt (non-interactive)."
        Write-Info "Start the gateway later with: marcel gateway"
        return
    }

    $response = Read-Host "Would you like to start the gateway now? [Y/n]"

    if ($response -eq "" -or $response -match "^[Yy]") {
        Write-Info "Starting gateway in background..."
        try {
            $logFile = "$MarcelHome\logs\gateway.log"
            Start-Process -FilePath $marcelCmd -ArgumentList "gateway" `
                -RedirectStandardOutput $logFile `
                -RedirectStandardError "$MarcelHome\logs\gateway-error.log" `
                -WindowStyle Hidden
            Write-Success "Gateway started! Your bot is now online."
            Write-Info "Logs: $logFile"
            Write-Info "To stop: close the gateway process from Task Manager"
        } catch {
            Write-Warn "Failed to start gateway. Run manually: marcel gateway"
        }
    } else {
        Write-Info "Skipped. Start the gateway later with: marcel gateway"
    }
}

function Write-Completion {
    Write-Host ""
    Write-Host "+---------------------------------------------------------+" -ForegroundColor Green
    Write-Host "|              [OK] Installation Complete!                |" -ForegroundColor Green
    Write-Host "+---------------------------------------------------------+" -ForegroundColor Green
    Write-Host ""
    
    # Show file locations
    Write-Host "* Your files:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Config:    " -NoNewline -ForegroundColor Yellow
    Write-Host "$MarcelHome\config.yaml"
    Write-Host "   API Keys:  " -NoNewline -ForegroundColor Yellow
    Write-Host "$MarcelHome\.env"
    Write-Host "   Data:      " -NoNewline -ForegroundColor Yellow
    Write-Host "$MarcelHome\cron\, sessions\, logs\"
    Write-Host "   Code:      " -NoNewline -ForegroundColor Yellow
    Write-Host "$MarcelHome\marcel-agent\"
    Write-Host ""
    
    Write-Host "---------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "* Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   marcel              " -NoNewline -ForegroundColor Green
    Write-Host "Start chatting"
    Write-Host "   marcel setup        " -NoNewline -ForegroundColor Green
    Write-Host "Configure API keys & settings"
    Write-Host "   marcel config       " -NoNewline -ForegroundColor Green
    Write-Host "View/edit configuration"
    Write-Host "   marcel config edit  " -NoNewline -ForegroundColor Green
    Write-Host "Open config in editor"
    Write-Host "   marcel gateway      " -NoNewline -ForegroundColor Green
    Write-Host "Start messaging gateway (Telegram, Discord, etc.)"
    Write-Host "   marcel update       " -NoNewline -ForegroundColor Green
    Write-Host "Update to latest version"
    Write-Host ""
    
    Write-Host "---------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[*] Restart your terminal for PATH changes to take effect" -ForegroundColor Yellow
    Write-Host ""
    
    if (-not $HasNode) {
        Write-Host "Note: Node.js could not be installed automatically." -ForegroundColor Yellow
        Write-Host "Browser tools need Node.js. Install manually:" -ForegroundColor Yellow
        Write-Host "  https://nodejs.org/en/download/" -ForegroundColor Yellow
        Write-Host ""
    }
    
    if (-not $HasRipgrep) {
        Write-Host "Note: ripgrep (rg) was not installed. For faster file search:" -ForegroundColor Yellow
        Write-Host "  winget install BurntSushi.ripgrep.MSVC" -ForegroundColor Yellow
        Write-Host ""
    }
}

# ============================================================================
# Stage protocol
# ============================================================================
#
# install.ps1 supports a small, stable "stage protocol" that lets programmatic
# callers (the desktop GUI's onboarding wizard, CI, future install.sh, etc.)
# drive the install one step at a time and surface progress/errors with their
# own UI.  CLI users running the canonical `irm | iex` one-liner never
# encounter this -- default invocation behaves exactly as before.
#
# Entry points:
#
#   install.ps1                       Interactive install (today's behavior).
#   install.ps1 -ProtocolVersion      Emit the protocol version integer.
#   install.ps1 -Manifest             Emit the stage manifest as JSON.
#   install.ps1 -Stage <name>         Run one stage and emit its result.
#   install.ps1 -NonInteractive       Disable all Read-Host prompts (also
#                                     skips the setup wizard and the gateway
#                                     autostart prompt).  Can be combined
#                                     with default invocation to do a full
#                                     non-interactive install.
#   install.ps1 -Json                 Emit machine-readable JSON instead of
#                                     the human-readable success banner at
#                                     the end of a full install.
#
# Manifest schema (the JSON returned by -Manifest):
#
#   {
#     "protocol_version": 1,
#     "stages": [
#       {
#         "name": "uv",
#         "title": "Installing uv package manager",
#         "category": "prereqs",
#         "needs_user_input": false
#       },
#       ...
#     ]
#   }
#
# Stage result (the JSON written by -Stage <name>):
#
#   {
#     "stage": "uv",
#     "ok": true,
#     "skipped": false,
#     "reason": null,
#     "duration_ms": 1234
#   }
#
# Exit codes:
#
#   0 -- success (stage ran, or stage was deliberately skipped).
#   1 -- generic failure; the stage threw.
#   2 -- unknown stage name passed to -Stage.
#
# Adding a stage:
#
#   1. Append an entry to $InstallStages below.
#   2. Make sure the worker function it points at is idempotent and respects
#      $NonInteractive when it has prompts.  Add it before "configure"
#      (the wizard) or "gateway" (autostart) if it should run unconditionally;
#      after those if it's optional post-install glue.
#   3. Do NOT bump $InstallStageProtocolVersion -- adding stages is additive.
#      Drivers iterate the manifest dynamically.
#
# ============================================================================

# Stage definitions -- the single source of truth.  Each entry maps a stable
# stage name (the API contract drivers depend on) to the worker function that
# implements it.  ``Title`` is what UIs show; ``Category`` lets UIs group
# stages; ``NeedsUserInput`` tells UIs "this stage prompts -- either skip it
# or arrange to provide answers another way."
$InstallStages = @(
    @{ Name = "uv";               Title = "Installing uv package manager";        Category = "prereqs";      NeedsUserInput = $false; Worker = "Stage-Uv" }
    @{ Name = "git";              Title = "Installing Git";                       Category = "prereqs";      NeedsUserInput = $false; Worker = "Stage-Git" }
    @{ Name = "node";             Title = "Detecting Node.js";                    Category = "prereqs";      NeedsUserInput = $false; Worker = "Stage-Node" }
    @{ Name = "system-packages";  Title = "Installing ripgrep and ffmpeg";        Category = "prereqs";      NeedsUserInput = $false; Worker = "Stage-SystemPackages" }
    @{ Name = "repository";       Title = "Cloning Marcel repository";            Category = "install";      NeedsUserInput = $false; Worker = "Stage-Repository" }
    # Managed Python lives under $InstallDir\.marcel-runtime, so the checkout
    # must exist before this stage creates that directory. Otherwise the later
    # repository stage treats the runtime-only directory as a broken checkout,
    # parks it, and leaves Stage-Venv with no managed interpreter.
    @{ Name = "python";           Title = "Verifying Python $PythonVersion";      Category = "prereqs";      NeedsUserInput = $false; Worker = "Stage-Python" }
    @{ Name = "venv";             Title = "Creating Python virtual environment";  Category = "install";      NeedsUserInput = $false; Worker = "Stage-Venv" }
    @{ Name = "dependencies";     Title = "Installing Python dependencies";       Category = "install";      NeedsUserInput = $false; Worker = "Stage-Dependencies" }
    @{ Name = "node-deps";        Title = "Installing Node.js dependencies";      Category = "install";      NeedsUserInput = $false; Worker = "Stage-NodeDeps" }
)
if ($IncludeDesktop) {
    # Insert AFTER node-deps so workspace npm is already installed when
    # the desktop build runs. Inserted only when explicitly requested
    # (Marcel-Setup.exe), never via the irm|iex CLI one-liner.
    $InstallStages += @{ Name = "desktop"; Title = "Building desktop app"; Category = "install"; NeedsUserInput = $false; Worker = "Stage-Desktop" }
}
$InstallStages += @(
    @{ Name = "path";             Title = "Adding Marcel to PATH";                Category = "finalize";     NeedsUserInput = $false; Worker = "Stage-Path" }
    @{ Name = "config-templates"; Title = "Writing configuration templates";      Category = "finalize";     NeedsUserInput = $false; Worker = "Stage-ConfigTemplates" }
    @{ Name = "platform-sdks";    Title = "Installing messaging platform SDKs";   Category = "finalize";     NeedsUserInput = $false; Worker = "Stage-PlatformSdks" }
    @{ Name = "bootstrap-marker"; Title = "Marking install complete";              Category = "finalize";     NeedsUserInput = $false; Worker = "Stage-BootstrapMarker" }
    # Interactive stages.  In non-interactive mode these become no-ops; the
    # caller (GUI / CI) handles the equivalent UX themselves.
    @{ Name = "configure";        Title = "Configuring API keys and models";      Category = "post-install"; NeedsUserInput = $true;  Worker = "Stage-Configure" }
    @{ Name = "gateway";          Title = "Starting messaging gateway";           Category = "post-install"; NeedsUserInput = $true;  Worker = "Stage-Gateway" }
)

# Stage workers -- thin wrappers that delegate to the existing Install-* /
# Test-* / Invoke-* functions while preserving their error semantics.  Kept
# as a separate layer so the existing functions remain callable directly
# (helpful for one-off recovery: ``. install.ps1; Install-Venv``).
#
# Stages that depend on uv (anything after Stage-Uv) call Resolve-UvCmd
# first so they work in cross-process driver mode where $script:UvCmd
# set by Stage-Uv in a sibling powershell process is not visible here.
# Resolve-UvCmd is a fast no-op when $script:UvCmd is already populated
# (the default-invocation case where Main runs everything in one
# process), and throws cleanly if uv truly isn't installed yet.
function Stage-Uv               { if (-not (Install-Uv))     { throw "uv installation failed" } }
function Stage-Python           { Resolve-UvCmd; if (-not (Test-Python))    { throw "Python $PythonVersion not available" } }
function Stage-Git              {
    if (-not (Install-Git)) {
        if ($script:GitInstallFailureReason) { throw $script:GitInstallFailureReason }
        throw "Git not available and auto-install failed -- install from https://git-scm.com/download/win then re-run"
    }
}
# Node is optional (browser tools degrade gracefully without it).  Surface
# failure to the JSON contract as skipped=true / reason rather than ok=true,
# so a GUI driver consuming the manifest can distinguish "node ready" from
# "node missing".  Install flow continues either way -- matches the
# existing Write-Completion behavior that prints a "Note: Node.js could
# not be installed" hint instead of aborting.
function Stage-Node             {
    if (-not (Test-Node)) {
        $script:_StageSkippedReason = "Node.js not available; browser tools will be unavailable until node is installed manually from https://nodejs.org/en/download/"
    }
}
function Stage-SystemPackages   { Install-SystemPackages }
function Stage-Repository       { Install-Repository }
function Stage-Venv             { Resolve-UvCmd; Install-Venv }
function Stage-Dependencies     { Resolve-UvCmd; Install-Dependencies }
function Stage-NodeDeps         { Install-NodeDeps }
function Stage-Desktop          { Install-DesktopVoiceDeps; Install-Desktop }
function Stage-Path             { Set-PathVariable }
function Stage-ConfigTemplates  { Copy-ConfigTemplates }
function Stage-PlatformSdks     { Resolve-UvCmd; Install-PlatformSdks }
function Stage-BootstrapMarker  { Write-BootstrapMarker }
function Stage-Configure        { Invoke-SetupWizard }
function Stage-Gateway          { Start-GatewayIfConfigured }

function Get-InstallStage {
    param([string]$Name)
    foreach ($s in $InstallStages) {
        if ($s.Name -eq $Name) { return $s }
    }
    return $null
}

function Step-OutOfInstallDir {
    # Windows refuses to delete a directory any shell is currently cd'd
    # inside -- and silently leaves orphan files behind, which then wedge
    # "is this a valid git repo" probes on re-install.  Harmless when the
    # caller ran the installer from somewhere else.
    try {
        $currentResolved = (Get-Location).ProviderPath
        $installResolved = $null
        if (Test-Path $InstallDir) {
            $installResolved = (Resolve-Path $InstallDir -ErrorAction SilentlyContinue).ProviderPath
        }
        if ($installResolved -and $currentResolved.ToLower().StartsWith($installResolved.ToLower())) {
            Write-Info "Stepping out of $InstallDir so Windows can replace files there if needed..."
            Set-Location $env:USERPROFILE
        }
    } catch {}
}

function Invoke-Stage {
    param(
        [Parameter(Mandatory=$true)] [hashtable]$StageDef
    )

    # Refresh PATH from registry so this stage sees binaries installed by
    # prior stages, even when each stage runs in its own powershell process.
    # No-op in cost-relevant cases (default invocation path syncs once per
    # foreach pass; cross-process drivers get the necessary freshening).
    Sync-EnvPath

    # Per-stage soft-skip channel.  A worker can populate
    # $script:_StageSkippedReason to surface "ran, but the thing it was
    # supposed to set up is not available" as skipped=true in the JSON
    # frame, without throwing.  Used by Stage-Node so the install flow
    # doesn't abort when an optional capability is missing while still
    # being honest in the protocol contract.  Reset before each stage so
    # a prior stage's reason can never leak into a later stage's frame.
    $script:_StageSkippedReason = $null

    $start = [DateTime]::UtcNow
    $result = @{
        stage        = $StageDef.Name
        ok           = $false
        skipped      = $false
        reason       = $null
        duration_ms  = 0
    }

    try {
        & $StageDef.Worker
        $result.ok = $true
        if ($script:_StageSkippedReason) {
            $result.skipped = $true
            $result.reason  = $script:_StageSkippedReason
        }
    } catch {
        $result.ok = $false
        $result.reason = "$_"
        throw
    } finally {
        $result.duration_ms = [int]([DateTime]::UtcNow - $start).TotalMilliseconds
        if ($Json -or $Stage) {
            # In stage-driver mode every stage emits a JSON line so the
            # caller can stream progress.  In default interactive mode we
            # stay silent here (the worker already wrote human output).
            $result | ConvertTo-Json -Compress | Write-Output
            # Tell the entry-point catch that we've already emitted a
            # frame for this failure (when $result.ok = $false), so it
            # doesn't double-emit a second JSON object and break the
            # one-line-per-stage contract the driver protocol promises.
            if (-not $result.ok) {
                $script:_StageEmittedErrorFrame = $true
            }
        }
    }
}

# ============================================================================
# Main
# ============================================================================

function Invoke-AllStages {
    Step-OutOfInstallDir
    foreach ($s in $InstallStages) {
        Invoke-Stage -StageDef $s
    }
}

function Invoke-EnsureMode {
    param([string]$Deps)
    $depList = $Deps -split ","
    foreach ($dep in $depList) {
        $dep = $dep.Trim()
        switch ($dep) {
            "node" {
                [void](Test-Node)
                if (-not $script:HasNode) {
                    Write-Err "Node.js could not be installed"
                    exit 1
                }
            }
            "browser" {
                [void](Test-Node)
                if ($script:HasNode) {
                    Install-AgentBrowser
                } else {
                    Write-Err "Node.js is required for browser tools but could not be installed"
                    exit 1
                }
            }
            "ripgrep" {
                Write-Info "ripgrep: install manually on Windows (scoop install ripgrep)"
            }
            "ffmpeg" {
                Write-Info "ffmpeg: install manually on Windows (scoop install ffmpeg)"
            }
            default {
                Write-Err "Unknown dependency: $dep"
                exit 1
            }
        }
    }
}

function Invoke-PostInstallMode {
    Write-Info "Running post-install setup..."
    Invoke-EnsureMode -Deps "node,browser"
    Write-Info "Post-install complete"
}

function Main {
    Write-Banner
    Invoke-AllStages
    if (-not $Json) {
        Write-Completion
    } else {
        @{ ok = $true; protocol_version = $InstallStageProtocolVersion } | ConvertTo-Json -Compress | Write-Output
    }
}

# ----------------------------------------------------------------------------
# Entry-point dispatch
# ----------------------------------------------------------------------------
#
# All branches funnel through one try/catch so errors don't kill an `irm |
# iex` PowerShell session, and so failures in stage-driver mode produce a
# structured JSON error frame instead of a bare exception.

# Dot-sourcing loads the installer's real functions for isolated behavioral
# tests without running an install. Normal script and `irm | iex` entry points
# are unchanged.
if ($MyInvocation.InvocationName -eq ".") {
    return
}

try {
    if (-not ($ProtocolVersion -or $ShowResolvedPaths -or $Manifest)) {
        Invoke-LegacyMigrationPrecondition
    }
    if ($Ensure -ne "") {
        if ($PSBoundParameters.ContainsKey("Stage")) {
            Write-Err "Cannot use -Ensure and -Stage simultaneously"
            exit 1
        }
        Invoke-EnsureMode -Deps $Ensure
        exit 0
    }
    if ($PostInstall) {
        Invoke-PostInstallMode
        exit 0
    }

    if ($ProtocolVersion) {
        Write-Output $InstallStageProtocolVersion
        exit 0
    }

    if ($ShowResolvedPaths) {
        $script:ResolvedPathReport | ConvertTo-Json -Depth 5 -Compress | Write-Output
        exit 0
    }

    if ($Manifest) {
        $payload = @{
            protocol_version = $InstallStageProtocolVersion
            stages = @($InstallStages | ForEach-Object {
                @{
                    name             = $_.Name
                    title            = $_.Title
                    category         = $_.Category
                    needs_user_input = $_.NeedsUserInput
                }
            })
        }
        $payload | ConvertTo-Json -Depth 5 -Compress | Write-Output
        exit 0
    }

    # Use PSBoundParameters rather than $Stage truthiness so that an
    # explicit `-Stage ""` from a misbehaving driver doesn't fall through
    # to the full-install Main path and silently kick off a destructive
    # operation.  Empty string is a contract violation; surface it as
    # unknown-stage exit 2 with a structured JSON frame.
    if ($PSBoundParameters.ContainsKey("Stage")) {
        $def = Get-InstallStage -Name $Stage
        if (-not $def) {
            $err = @{
                ok     = $false
                stage  = $Stage
                reason = "unknown stage: $Stage. Run install.ps1 -Manifest to list valid stages."
            }
            $err | ConvertTo-Json -Compress | Write-Output
            exit 2
        }
        Step-OutOfInstallDir
        Invoke-Stage -StageDef $def
        exit 0
    }

    # Default: full install (today's behavior, plus optional -NonInteractive
    # and -Json layered on by the params above).
    Main
} catch {
    if ($Json -or $Stage) {
        # Stage-driver mode: caller wants JSON they can parse.  Emit a
        # structured error frame and exit non-zero -- BUT only if
        # Invoke-Stage didn't already emit one for this same failure.
        # The inner finally emits the authoritative per-stage frame
        # (with duration_ms + skipped fields); a second emit here
        # would produce two concatenated JSON objects on stdout and
        # break drivers that parse one-line-per-invocation.
        if (-not $script:_StageEmittedErrorFrame) {
            $err = @{
                ok     = $false
                stage  = if ($Stage) { $Stage } else { $null }
                reason = "$_"
            }
            $err | ConvertTo-Json -Compress | Write-Output
        }
        exit 1
    }

    # Interactive mode: keep today's friendly recovery hint.
    Write-Host ""
    Write-Err "Installation failed: $_"
    Write-Host ""
    Write-Info "If the error is unclear, try downloading and running the script directly:"
    Write-Host "  Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/AIMarce1a/marcel-agent/main/scripts/install.ps1' -OutFile install.ps1" -ForegroundColor Yellow
    Write-Host "  .\install.ps1" -ForegroundColor Yellow
    Write-Host ""
}
