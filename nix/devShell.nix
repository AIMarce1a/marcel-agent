# nix/devShell.nix — Dev shell that delegates setup to each package
#
# Each npm workspace package exposes passthru.packageJsonPath (e.g.
# "ui-tui/package.json").  This file collects them all and passes the
# list to mkNpmDevShellHook, which stamps all package.jsons at once,
# then runs a single `npm i --package-lock-only` if any changed and
# `npm ci` if the lockfile changed.
{ ... }:
{
  perSystem =
    { pkgs, self', ... }:
    let
      packages = builtins.attrValues self'.packages;
      marcelNpmLib = self'.packages.default.passthru.marcelNpmLib;

      # Collect all packageJsonPath values from npm workspace packages.
      npmPackageJsonPaths = builtins.filter (p: p != null) (
        map (p: p.passthru.packageJsonPath or null) packages
      );

      marcelAgentDevShellHook = self'.packages.default.passthru.devShellHook;
    in
    {
      devShells.default = pkgs.mkShell {
        packages = with pkgs; [
          (pkgs.runCommand "marcel" { } ''
            mkdir -p $out/bin
            install -Dm755 ${../marcel} $out/bin/marcel
          '')
          self'.packages.sandbox
          uv
          # Headless Wayland compositor for E2E tests (test:e2e:visual).
          # cage renders a single client with no window management, so
          # the Electron window opens at a fixed size without tiling.
          # libglvnd provides libEGL.so.1 that cage needs on NixOS.
          cage
          libglvnd
          # Graphical terminal + Wayland screenshot client for CLI/TUI UI
          # evidence. `cage -- ghostty ...` keeps captures off the user's
          # live compositor; grim runs inside that isolated client session.
          ghostty
          grim
        ]
        ++ self'.packages.default.passthru.devDeps;
        shellHook = ''
          ${marcelAgentDevShellHook}
          ${marcelNpmLib.mkNpmDevShellHook npmPackageJsonPaths}

          # Force Node to use Nix's playwright-test binary instead of node_modules/.bin
          export PATH="${pkgs.playwright-test}/bin:$PATH"

          # for the devshell to pick up the src
          export MARCEL_PYTHON_SRC_ROOT=$(git rev-parse --show-toplevel)

          # Let `uv run --active --no-sync` reuse Nix's provisioned Python
          # environment instead of creating an empty project .venv.
          export VIRTUAL_ENV="$(dirname "$(dirname "$(readlink -f "$(command -v python)")")")"

          echo "Marcel Agent dev shell in $MARCEL_PYTHON_SRC_ROOT"
          echo "Ready. Run 'marcel' or 'sandbox marcel' to start."
        '';
      };
    };
}
