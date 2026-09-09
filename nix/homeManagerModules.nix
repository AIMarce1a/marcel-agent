# nix/homeManagerModules.nix — the Home Manager module for marcel-agent
#
# This module is the user-level equivalent of nixosModules.default. Marcel is
# an agent for one person. The credentials, the memory, the sessions and the
# cron jobs all belong to that person. Thus a user-level module is correct on
# each distribution, and not only on NixOS.
#
# `services.marcel-agent` is the same option set on both modules. All of the
# options except the system-level ones come from nix/moduleCommon.nix, so an
# example from the NixOS documentation works here without a change. Only the
# necessary parts are different:
#
#   removed   user, group, createUser  — Home Manager runs as the user
#   removed   container.*              — it needs root and the Docker socket
#   removed   UMask 0007               — that mode shares state with a UNIX
#                                        group, but this state has one user
#   changed   systemd.services         -> systemd.user.services or
#                                        launchd.agents
#   changed   system.activationScripts -> home.activation
#   changed   addToSystemPackages      -> programs.marcel-agent.enable and
#                                        home.sessionVariables
#   added     programs.marcel-agent    the CLI and the desktop application,
#                                      because Home Manager separates an
#                                      installation from a daemon
#   changed   stateDir (+ "/.marcel")  -> marcelHome, set directly
#
# To use the module:
#   imports = [ marcel-agent.homeManagerModules.default ];
#   programs.marcel-agent = {
#     enable = true;          # the marcel CLI on your PATH
#     desktop.enable = true;  # the Electron application and a launcher
#   };
#   services.marcel-agent = {
#     enable = true;
#     gateway.enable = true;
#     settings.model.default = "anthropic/claude-sonnet-4";
#     environmentFiles = [ config.sops.secrets."marcel/env".path ];
#   };
#
# CAUTION: Enable linger for the account. Without linger, systemd stops the
# user manager at logout, and both units stop with it. Home Manager cannot
# run `loginctl enable-linger`. On NixOS, set
#   users.users.<name>.linger = true;
# On other systems, run `loginctl enable-linger <name>` one time.
{ inputs, ... }:
{
  flake.homeManagerModules.default =
    {
      config,
      lib,
      options,
      pkgs,
      ...
    }:

    let
      cfg = config.services.marcel-agent;
      cfgPrograms = config.programs.marcel-agent;
      common = import ./moduleCommon.nix { inherit lib; };

      effectivePackage = common.effectivePackage cfg;
      marcel-agent = inputs.self.packages.${pkgs.stdenv.hostPlatform.system}.default;

      inherit (pkgs.stdenv.hostPlatform) isDarwin isLinux;

      processEnvironment = common.processEnvironment {
        inherit (cfg) marcelHome;
        # The CLI reads this value and names it when it refuses a
        # configuration change.
        managedSystem = "home-manager";
      };
      unitPath = lib.makeBinPath (common.processPath { inherit pkgs cfg; });

      # ── The desktop launcher ───────────────────────────────────────────
      # A GUI launcher reads no shell profile, so home.sessionVariables does
      # not reach it, and the application would open ~/.marcel while the
      # services use marcelHome. Thus the launcher carries the value itself.
      #
      # MARCEL_MANAGED rides along only when the services are enabled. That
      # variable makes the CLI refuse a configuration change and name the
      # rebuild command. A person who enables `programs.` alone has no
      # activation and no managed configuration, so the application must not
      # claim one and refuse an edit that nothing else owns.
      desktopEnvironment = {
        MARCEL_HOME = cfg.marcelHome;
      }
      // lib.optionalAttrs cfg.enable {
        inherit (processEnvironment) MARCEL_MANAGED;
      }
      // lib.optionalAttrs desktopUsesService {
        MARCEL_DESKTOP_REMOTE_URL = "http://${cfg.backend.host}:${toString cfg.backend.port}";
      };

      # The application reaches the backend of the service only when there is
      # a backend to reach AND a shared token to present with. Without the
      # token the desktop resolver throws ("MARCEL_DESKTOP_REMOTE_URL is set
      # but MARCEL_DESKTOP_REMOTE_TOKEN is not"), so the two variables travel
      # together or not at all.
      desktopUsesService = cfg.enable && cfg.backend.mode != "none" && cfg.backend.sessionTokenFile != null;

      # The token is read at start time and never with `--set`. makeWrapper
      # writes a --set value into the Nix store, which all users can read.
      desktopRun = lib.optional desktopUsesService ''
        if [ -r ${lib.escapeShellArg cfg.backend.sessionTokenFile} ]; then
          MARCEL_DESKTOP_REMOTE_TOKEN="$(tr -d '\r\n' < ${lib.escapeShellArg cfg.backend.sessionTokenFile})"
          export MARCEL_DESKTOP_REMOTE_TOKEN
        else
          echo "marcel-desktop: cannot read the session token at ${cfg.backend.sessionTokenFile}." >&2
          echo "marcel-desktop: the application starts its own backend instead of the one of the service." >&2
        fi
      '';

      # `override`, and not `overrideAttrs`: the values go into the wrapper
      # that the installPhase writes, and not into a derivation attribute.
      desktopPackage = cfgPrograms.desktop.package.override {
        extraEnv = desktopEnvironment;
        extraRun = desktopRun;
      };

      # The systemd unit that the gateway and the backend both start from.
      mkUnit =
        {
          description,
          argv,
        }:
        {
          Unit = {
            Description = description;
            # Do not use network-online.target here. That is a system target.
            # A user unit that orders against it has no effect, and systemd
            # gives no message.
            After = [ "default.target" ];
          };
          Install.WantedBy = [ "default.target" ];
          Service = {
            Type = "simple";
            Environment = (lib.mapAttrsToList (k: v: "${k}=${v}") processEnvironment) ++ [
              "PATH=${unitPath}"
            ];
            ExecStart = lib.escapeShellArgs argv;
            WorkingDirectory = cfg.workingDirectory;
            Restart = cfg.restart;
            RestartSec = cfg.restartSec;
            # This state has one user. Keep it private. The NixOS module uses
            # 0007 to share the state with a UNIX group.
            UMask = "0077";
            NoNewPrivileges = true;
            PrivateTmp = true;
          };
        };

      mkAgent =
        { argv, logName }:
        {
          enable = true;
          config = {
            Label = "org.nix-community.home.${logName}";
            ProgramArguments = argv;
            EnvironmentVariables = processEnvironment // {
              PATH = "${unitPath}:/usr/bin:/bin:/usr/sbin:/sbin";
            };
            WorkingDirectory = cfg.workingDirectory;
            RunAtLoad = true;
            KeepAlive =
              if cfg.restart == "always" then
                true
              else
                {
                  SuccessfulExit = false;
                  Crashed = true;
                };
            ThrottleInterval = cfg.restartSec;
            StandardOutPath = "${config.home.homeDirectory}/Library/Logs/${logName}.log";
            StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/${logName}.err.log";
            ProcessType = "Background";
          };
        };

    in
    {
      # ── programs.marcel-agent — the installation ───────────────────────
      # Home Manager separates "install this application for me" from "run
      # this daemon". Marcel needs both, and a person can want one without
      # the other: an application with no gateway, or a headless gateway on
      # a machine with no display.
      #
      # `services.marcel-agent` stays the authority for the state and the
      # configuration. This module reads marcelHome and the backend address
      # from it, and never the reverse.
      options.programs.marcel-agent = {
        enable = lib.mkEnableOption ''
          the Marcel Agent command line application.

          This adds `marcel` to home.packages, and exports MARCEL_HOME with
          home.sessionVariables. An interactive shell then uses the same
          state as `services.marcel-agent`
        '';

        package = lib.mkOption {
          type = lib.types.package;
          default = effectivePackage;
          defaultText = lib.literalExpression "config.services.marcel-agent.package";
          description = ''
            The marcel-agent package to install.

            The default follows `services.marcel-agent.package`, and applies
            `extraPythonPackages` and `extraDependencyGroups` from that
            module. Thus the command line and the services are one build,
            and a plugin that the services can load is a plugin that your
            shell can load.
          '';
        };

        desktop = {
          enable = lib.mkEnableOption ''
            the Marcel Desktop application (Electron).

            This adds `marcel-desktop` to home.packages, with an XDG
            launcher entry on Linux. The launcher starts the same Marcel
            runtime that `package` gives, and reads the MARCEL_HOME of
            `services.marcel-agent`. Thus the application, the interactive
            shell and the services share one state directory.

            The Electron application carries its own Marcel runtime with
            the usual distribution. This module gives it the Nix package
            instead, with MARCEL_DESKTOP_MARCEL. It installs no second copy
            of Marcel, and it downloads nothing on the first start
          '';

          package = lib.mkOption {
            type = lib.types.package;
            default = cfgPrograms.package.marcelDesktop;
            defaultText = lib.literalExpression "config.programs.marcel-agent.package.marcelDesktop";
            description = ''
              The marcel-desktop package to use.

              The default follows `package`, and thus also
              `services.marcel-agent.extraPythonPackages` and
              `extraDependencyGroups`, because the desktop application is a
              passthru of the agent package. A package that you set here
              carries its own Marcel runtime, and this module cannot make
              it agree with the services.
            '';
          };
        };
      };

      options.services.marcel-agent =
        common.sharedOptions {
          defaultPackage = marcel-agent;
          defaultPackageText = lib.literalExpression "marcel-agent.packages.\${system}.default";
          defaultWorkingDirectory = config.home.homeDirectory;
          defaultWorkingDirectoryText = lib.literalExpression "config.home.homeDirectory";
        }
        // {
          marcelHome = lib.mkOption {
            type = lib.types.str;
            default = "${config.home.homeDirectory}/.marcel";
            defaultText = lib.literalExpression ''"''${config.home.homeDirectory}/.marcel"'';
            description = ''
              The value of MARCEL_HOME. This state directory holds
              config.yaml, .env, auth.json, the sessions, the skills, the
              memory and the cron jobs.

              The NixOS module takes a `stateDir` and adds `/.marcel` to it.
              This module sets MARCEL_HOME directly. Thus an existing
              ~/.marcel continues to work, and you can give the directory any
              name.
            '';
            example = "/home/alice/.marcel-work";
          };

          # `installPackage` moved to `programs.marcel-agent.enable`. The
          # option is dead, but it must not be silent: it defaulted to true,
          # so a person who never named it still got the command line, and a
          # quiet removal gives them a machine with no `marcel` and no
          # message. mkOption with an assertion, and not
          # mkRemovedOptionModule, because the message must name the exact
          # replacement for the value they set.
          installPackage = lib.mkOption {
            type = lib.types.nullOr lib.types.bool;
            default = null;
            visible = false;
            description = ''
              Removed. Use `programs.marcel-agent.enable` instead.
            '';
          };

          gateway.enable = lib.mkEnableOption "the messaging gateway service (Telegram, Discord, Slack, ...)";
        };

      config = lib.mkMerge [

        # ── programs.marcel-agent — the installation ──────────────────────
        # Outside the `services.enable` guard on purpose. A person can want
        # the command line or the application on a machine that runs no
        # daemon at all.
        (lib.mkIf cfgPrograms.enable {
          home.packages = [ cfgPrograms.package ];
          home.sessionVariables.MARCEL_HOME = cfg.marcelHome;
        })

        # A launcher from the desktop menu reads no shell profile, so the
        # MARCEL_HOME that `programs.enable` exports does not reach it. Home
        # Manager writes only systemd.user.sessionVariables into
        # environment.d, and this module does not put MARCEL_HOME there,
        # because that file applies to each user unit. Thus the launcher
        # carries the value itself. See desktopEnvironment above.
        (lib.mkIf cfgPrograms.desktop.enable {
          home.packages = [ desktopPackage ];
        })

        {
          assertions = [
            {
              # `installPackage` was removed in favour of the programs/services
              # split. It defaulted to true, so a quiet removal leaves a person
              # with no `marcel` on the PATH and no message.
              assertion = cfg.installPackage == null;
              message = common.installPackageRemovedMessage cfg.installPackage;
            }
          ];
        }

        (lib.mkIf cfg.enable (
          lib.mkMerge [

            # ── Merge MCP servers into settings ────────────────────────────
            (lib.mkIf (cfg.mcpServers != { }) {
              services.marcel-agent.settings.mcp_servers = common.mcpServersToConfig cfg.mcpServers;
            })

            {
              assertions =
                common.pluginNameAssertions {
                  inherit cfg;
                  optionPath = "services.marcel-agent";
                }
                ++ common.workspaceFilesAssertions {
                  inherit cfg;
                  opt = options.services.marcel-agent.workingDirectory;
                  optionPath = "services.marcel-agent";
                }
                ++ common.backendBindAssertions {
                  inherit cfg;
                  optionPath = "services.marcel-agent";
                }
                ++ [
                  {
                    # The interface poll reads `ip`, which iproute2 supplies on
                    # Linux only.
                    assertion = !isDarwin || cfg.backend.waitFor != "interface";
                    message = "services.marcel-agent.backend.waitFor = \"interface\" works on Linux only. Use \"hostname\" on Darwin.";
                  }
                ];
            }

            # The agent runs these tools, so they belong on the PATH of the
            # person as well as in the unit.
            (lib.mkIf cfgPrograms.enable {
              home.packages = cfg.extraPackages;
            })

            # ── Activation: directories, config, secrets, documents ────────
            {
              # The activation runs after writeBoundary, when the home.file
              # symlinks are in place. It also runs after linkGeneration, when
              # Home Manager completes the switch. A secret that the activation
              # entry of sops-nix writes exists at that point.
              home.activation.marcelAgentSetup =
                lib.hm.dag.entryAfter
                  [
                    "writeBoundary"
                    "linkGeneration"
                  ]
                  (
                    common.mkStateScript {
                      inherit pkgs cfg;
                      inherit (cfg) marcelHome workingDirectory;
                      run = "$DRY_RUN_CMD ";
                      stateDirs = common.stateSubdirs;
                      managedSystem = "home-manager";
                      # This state has one user. No group needs access to it.
                      modes = {
                        config = "0600";
                        env = "0600";
                        managed = "0600";
                        auth = "0600";
                        document = "0600";
                      };
                    }
                  );
            }

            # ── Linux: systemd user services ───────────────────────────────
            (lib.mkIf (isLinux && cfg.gateway.enable) {
              systemd.user.services.marcel-agent = mkUnit {
                description = "Marcel Agent Gateway";
                argv = common.gatewayArgv cfg;
              };
            })

            (lib.mkIf (isLinux && cfg.backend.mode != "none") {
              systemd.user.services.marcel-backend = mkUnit {
                description = common.backendDescription cfg;
                argv = common.backendArgv { inherit pkgs cfg; };
              };
            })

            # ── Darwin: launchd agents ─────────────────────────────────────
            (lib.mkIf (isDarwin && cfg.gateway.enable) {
              launchd.agents.marcel-agent = mkAgent {
                argv = common.gatewayArgv cfg;
                logName = "marcel-agent";
              };
            })

            (lib.mkIf (isDarwin && cfg.backend.mode != "none") {
              launchd.agents.marcel-backend = mkAgent {
                argv = common.backendArgv { inherit pkgs cfg; };
                logName = "marcel-backend";
              };
            })
          ]
        ))
      ];
    };
}
