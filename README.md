# lifenote

> Bring your private [Life Note](https://www.mylifenote.ai) journal into your AI agents — Claude Code, Claude Desktop, Cursor, Codex, anything that speaks MCP.

Life Note becomes the **memory layer for your AI workflows.** Every reflection you've ever written becomes context your agents can quietly reach for, so you don't have to re-introduce yourself.

```bash
pipx install lifenote
lifenote auth login
```

That's it. From any Claude Code / Cursor / Claude Desktop session, you can now ask things like *"what have I been writing about lately?"* and the agent already knows you.

---

## What this unlocks

Real things you can ask, once connected:

> *"I have a hard conversation with my cofounder today. What have I been writing about her?"*

> *"I'm stuck. What was I trying to accomplish this month?"*

> *"What did Marcus Aurelius (or Jung, or my Inner Wisdom) say to me about anxiety?"*

> *"I remember saving a beautiful Jung line about words being vessels — find it."*

> *"Pre-board-meeting check: what's been weighing on me this week?"*

> *"What's my life aim, what's my focus this year, and what practices am I doing?"*

> *"I'm drafting a post about late-bloomer entrepreneurship. What have I journaled on this theme?"*

The agent figures out which tools to call. You just ask in plain English.

---

## Install

```bash
# Recommended
pipx install lifenote

# Or with pip
pip install lifenote
```

Requires Python 3.10+.

## Sign in

```bash
lifenote auth login
```

Browser opens, you click **Allow**, you're done. Your token is stored in your OS keychain (macOS Keychain / Windows Credential Manager / Linux libsecret) — never in plaintext.

For CI / Docker / headless agents, set `LIFENOTE_API_TOKEN` instead.

---

## Use from your terminal

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

---

## Connect to your AI agent

### Claude Desktop

Edit Claude Desktop's config file and add the `lifenote` MCP server:

| OS | Config path |
|---|---|
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Linux** | `~/.config/Claude/claude_desktop_config.json` |

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

### Claude Code

```bash
claude mcp add lifenote -- lifenote mcp
```

That's it. Open any Claude Code session and ask away.

### Claude.ai web (Connectors)

Settings → Connectors → **Add Connector** → paste:

```
https://mcp.mylifenote.ai/api/agent/v1/mcp
```

Approve the OAuth screen. No install needed.

### Cursor / Codex / other MCP clients

Same `command: lifenote, args: [mcp]` pattern, or point them at the HTTP endpoint directly.

---

## Install the bundled Claude Code skill

Teaches Claude Code *when* to reach for Life Note versus when not to (e.g. don't read your journal when you're debugging code):

```bash
lifenote skills install
```

Drops a markdown file into `~/.claude/skills/lifenote.md`. Edit to taste.

---

## What an agent can read

All read-only, scoped to your account:

- **journal:read** — your written entries, AI-generated analysis (themes, feelings), your Wisdom collection (passages you highlighted), your Practices & Quests with full context, your singular life aim, your yearly ambition theme.
- **chat:read** — your past conversations with mentors (Marcus Aurelius, Naval, your Inner Wisdom, etc.).

It **cannot** write to your journal, change your settings, see payment info, or access other users' data.

You can revoke any agent anytime at <https://www.mylifenote.ai/settings/agents>. Each connection has a separate revoke button.

---

## CLI command reference

```
lifenote auth login | logout | whoami
lifenote search <query> [--since 30d] [--limit 20] [--json]
lifenote entries [--since 7d] [--limit 20]
lifenote today | week
lifenote conversations list | show <id>
lifenote mcp                  # stdio MCP server entry point
lifenote skills install       # bundled Claude Code skill
lifenote version
```

---

## Configuration

Environment variables (all optional):

- `LIFENOTE_API_TOKEN` — bypass keychain (essential for CI / Docker)
- `LIFENOTE_BASE_URL` — point at staging / dev (default: `https://www.mylifenote.ai`)

---

## How this is different from "just an API"

| | "Search your journal" | **Life Note as memory layer** |
|---|---|---|
| What you ask | Specific queries | Conversational, contextual |
| What the agent knows about you | Nothing — you re-introduce yourself each session | Already knows your themes, your life aim, your saved wisdom |
| Result | Lookups | Calibrated responses |

The moat isn't the API. It's the years of writing already in your journal.

---

## Privacy

- All journal data is encrypted at rest with a per-user key.
- The CLI never stores plaintext tokens on disk — only in your OS keychain.
- Every agent connection is auditable at /settings/agents.
- We never train models on your data. We never share it with third parties.
- You can disconnect any agent (or all of them) with one click.

---

## License

MIT. Built by [Daniel W. Chen](https://github.com/dandanbang). Source: <https://github.com/dandanbang/lifenote-cli>. Issues + PRs welcome.
