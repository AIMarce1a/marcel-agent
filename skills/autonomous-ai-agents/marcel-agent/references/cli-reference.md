# Marcel CLI Reference

Live sources when anything looks stale: `marcel --help`, `marcel <command> --help`,
https://hermes-agent.nousresearch.com/docs/reference/cli-commands

### Global Flags

```
marcel [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
marcel chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
marcel setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
marcel model                Interactive model/provider picker
marcel fallback [add|remove|list]  Fallback provider chain
marcel config [show|edit|get|set|unset|path|env-path|check|migrate]
marcel login / logout       OAuth sign-in / clear stored auth
marcel doctor [--fix]       Check dependencies and config
marcel status [--all]       Component status
```

### Tools & Skills

```
marcel tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

marcel skills list|browse|search QUERY|inspect ID
marcel skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
marcel skills config        Enable/disable skills per platform
marcel skills check|update|uninstall|publish PATH
marcel skills tap add REPO  Add a GitHub repo as a skill source
marcel bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
marcel mcp add NAME (--url or --command) | remove | list | test NAME
marcel mcp catalog | install NAME     Curated catalog install
marcel mcp configure NAME             Toggle tool selection
marcel mcp serve                      Run Marcel as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
marcel gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `marcel photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
marcel sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
marcel cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
marcel webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
marcel profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
marcel profile rename A B | alias NAME | export NAME | import FILE
```

### Credentials & Pools

```
marcel auth                 Interactive credential manager
marcel auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
marcel auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
marcel desktop / gui        Native desktop app
marcel dashboard            Web admin panel + embedded chat (--stop / --status)
marcel proxy                OpenAI-compatible local proxy backed by an OAuth provider
marcel portal               Quick setup / sign in via Nous Portal
marcel kanban <verb>        Multi-agent work-queue board
marcel project              Named multi-folder workspaces
marcel skin list|use|set    Switch/tweak skins (see references/themes.md)
marcel pets <verb>          Pet mascots (see references/petdex.md)
marcel memory setup|status|off|reset   Memory provider
marcel secrets bitwarden|onepassword   External secret stores
marcel moa                  Mixture-of-Agents slots
marcel hooks / security / backup / import / checkpoints / console
marcel logs [-f] [errors]   View agent/error logs
marcel send                 One-off message through a gateway platform
marcel pairing / plugins / insights / journey / computer-use
marcel acp                  ACP server (IDE integration)
marcel completion bash|zsh|fish
marcel update / uninstall / claw migrate
```

Plugin- and provider-supplied subcommands (e.g. `marcel photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `marcel config edit` · [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) |
| Tools / toolsets | `marcel tools list` · [Tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference) |
| Skills catalog | `marcel skills browse` · [Skills catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `marcel model` · [Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers) |
| Env variables | `marcel config env-path` · [Env vars reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) |
| Gateway logs | `~/.marcel/logs/gateway.log` (or `marcel logs`) |
| Sessions | `marcel sessions browse` (reads state.db) |
