# lifenote

Bring your private [Life Note](https://www.mylifenote.ai) journal into your AI agents — Claude Code, Claude Desktop, Cursor, Codex, anything that speaks MCP.

## Install

```bash
pipx install lifenote      # recommended
# or
pip install lifenote
```

## Sign in

```bash
lifenote auth login
```

Opens your browser, you click **Allow**, you're done. Your token is stored in your OS keychain (macOS Keychain / Windows Credential Manager / Linux libsecret) — never in plain files.

For CI / Docker / headless agents, set `LIFENOTE_API_TOKEN` in the environment instead.

## Use it from the terminal

```bash
lifenote search "anxiety about launch"
lifenote entries --since 7d
lifenote today
lifenote week
lifenote conversations list
lifenote conversations show 574
```

Add `--json` to any command for piping into agents:

```bash
lifenote search "burnout" --json | claude "summarize the patterns"
```

## Use it from your AI agent (MCP)

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lifenote": {
      "command": "lifenote",
      "args": ["mcp"]
    }
  }
}
```

Restart Claude Desktop. Your journal is now a tool Claude can reach for on its own.

### Claude.ai web (Connectors)

Settings → Connectors → Add → paste `https://mcp.mylifenote.ai/api/agent/v1/mcp`. Approve the OAuth screen.

### Cursor / Codex / other MCP clients

Same `command: lifenote, args: [mcp]` pattern. Or point them at the HTTP endpoint directly.

## Bundled Claude Code skill

Drop a brand-aligned skill into your `~/.claude/skills/` so Claude Code knows when to reach for Life Note vs. when not to:

```bash
lifenote skills install
```

## What the agent can read

Two scopes today, both read-only:

- `journal:read` — your written entries + AI-generated analysis (themes, feelings)
- `chat:read` — your past conversations with mentors (Marcus Aurelius, etc.)

It **cannot** write to your journal, change your settings, see payment info, or access other users' data.

You can revoke any agent anytime at <https://www.mylifenote.ai/settings/agents>.

## Configuration

Environment variables (all optional):

- `LIFENOTE_API_TOKEN` — bypass keychain (essential for CI / Docker)
- `LIFENOTE_BASE_URL` — point at staging / dev (default: `https://www.mylifenote.ai`)

## License

MIT. Built by [Daniel W. Chen](https://github.com/dandanbang).
