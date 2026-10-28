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

Once connected, just ask in plain English — the agent figures out which tools to call. Not sure where to start? Match it to what you need:

**🌧️ Feeling down** — *"Look back through my journal and remind me of my small wins and the moments I actually grew — evidence I'm further along than I feel."*

**🔥 Angry or hurt** — *"I'm worked up about this. What have I written before about this person or situation — and what usually helps me settle?"*

**💡 Seeking clarity** — *"Across my recent entries, what are my top recurring patterns — and the triggers behind them?"*

**🌱 Looking to grow** — *"What blind spot keeps showing up in my writing — and what have my mentors said that speaks to it?"*

**🪧 Facing a decision** — *"I'm torn. Based on what I've written and my Life Goal, what do I actually value here?"*

**🧭 Feeling adrift** — *"What am I working on right now, and where am I drifting from this year's focus?"*

### Power-user asks

The 14 read-only tools compose, so you can chain them:

> *"Cross-reference my journal and my saved wisdom on burnout — where do they agree, where do they diverge?"*

> *"Pull my last month of entries and draft a weekly-review summary I can paste into my journal."*

> *"Given my Life Goal and this year's focus, what have I actually made progress on — with evidence from my entries?"*

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

### Unattended jobs: personal access tokens

A sign-in refreshes itself while you use it, but a weekly cron job needs something that just works. After `lifenote auth login`, create a **personal access token**:

```bash
lifenote token create --name "weekly obsidian sync" --expires 90d   # 30d | 90d | 365d
```

- It's **read-only**, and it is shown **once**. Life Note stores only a hash of it.
- Use it with `export LIFENOTE_TOKEN=ln_pat_…` (cron, CI, Docker). With that set, the CLI never touches the keychain. Or add `--save` to keep it in this machine's keychain as the default.
- `lifenote token list` shows each token's last use and expiry. `lifenote token revoke <id>` kills one at once.
- A token can't create or revoke tokens. Requesting account deletion revokes them all.

Check what this machine will use:

```bash
lifenote auth status     # who, which token, where it came from, days left
```

### Exit codes

| code | meaning |
|---|---|
| 0 | ok |
| 2 | usage: bad flag or value, or Life Note rejected the request as invalid |
| 3 | auth: not signed in, or the token is expired, revoked, or invalid |
| 4 | network: couldn't reach Life Note |
| 5 | server: Life Note returned an error, or rate-limited you |

Every failure prints one plain line to stderr.

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

### The full picture: Daily Insights + mentor replies

```bash
lifenote entries --since 7d --with-responses --json      # analysis + every mentor reply per entry
lifenote entries --updated-since 2026-10-20T00:00:00Z --reply-after-id 98765 --all --json   # only what changed
lifenote entries --after-id 12345 --all --json           # only entries newer than id 12345
```

`--updated-since` returns entries written or **edited** since that time, plus the other entries on those days, because a day's Daily Insight is shared and gets refreshed. `--reply-after-id` adds entries that got a **new mentor reply**. Every `--json` result carries `as_of` and `reply_cursor`: pass them back next time. `lifenote sync` does this for you.

### Export

```bash
lifenote export --since 2026-01-01 --until 2026-06-30 --format md --include-analysis --include-mentors -o journal.md
lifenote export --format csv --include-mentors -o journal.csv
lifenote export --since 30d --format json --include-analysis
```

### Weekly Obsidian sync

`lifenote sync <folder>` keeps a folder of Markdown notes in step with your journal: one note per entry (`2026/2026-10-28-12345.md`), YAML frontmatter (date, mood, mentors, feelings, topics, people), the Daily Insight, and each mentor reply as an Obsidian callout.

```bash
lifenote sync ~/Obsidian/MyVault/"Life Note"
```

- The first run pulls everything. Later runs fetch only entries written, edited, or given a new mentor reply since the last run, and refresh Daily Insights for those days. The cursor lives in the folder (`.lifenote-sync.json`).
- Re-running is safe: a note is rewritten only when it changed.
- Write your own thoughts **below the `%% Your notes below this line… %%` line** in any note; sync keeps them.
- Deleting an entry in Life Note does not delete its note. `--full` re-pulls everything.

**Run it every week.** Make a token once (`lifenote auth login`, then `lifenote token create --name "weekly obsidian sync" --expires 365d`), then:

*cron (Linux / macOS)*: `crontab -e`, add:

```cron
# Sundays 08:00. Use the full path from `which lifenote`.
LIFENOTE_TOKEN=ln_pat_paste_yours_here
0 8 * * 0  /usr/local/bin/lifenote sync "$HOME/Obsidian/MyVault/Life Note" >> "$HOME/.lifenote-sync.log" 2>&1
```

Exit code 3 in the log means the token expired or was revoked: make a new one.

*launchd (macOS)*: save as `~/Library/LaunchAgents/ai.mylifenote.sync.plist`, then `launchctl load ~/Library/LaunchAgents/ai.mylifenote.sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>ai.mylifenote.sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/lifenote</string>
    <string>sync</string>
    <string>/Users/YOU/Obsidian/MyVault/Life Note</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>LIFENOTE_TOKEN</key><string>ln_pat_paste_yours_here</string></dict>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/Users/YOU/.lifenote-sync.log</string>
  <key>StandardErrorPath</key><string>/Users/YOU/.lifenote-sync.log</string>
</dict>
</plist>
```

launchd runs a missed job when the Mac wakes; cron does not.

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
https://mcp.mylifenote.ai/mcp
```

Approve the OAuth screen. No install needed.

### ChatGPT (Pro / Team / Enterprise / Edu)

OpenAI added remote-MCP-server support in late 2025. Steps:

1. Open ChatGPT → **Settings → Apps & Connectors → Advanced settings**
2. Toggle **Developer Mode** ON
3. Back in Apps & Connectors → **Add new connector**
4. Name: `Life Note`, URL: `https://mcp.mylifenote.ai/mcp`
5. Authentication: **OAuth**, then confirm "I trust this application"

Free-tier ChatGPT doesn't support remote MCP servers yet — paid plans only.

### Gemini

Two paths, depending on which Gemini you use:

- **Gemini CLI** (Google's developer CLI): supports MCP natively. Configure `lifenote` as an MCP server in your Gemini CLI settings (`~/.gemini/settings.json` or similar) — same `command: lifenote, args: [mcp]` shape as Claude Desktop.
- **Gemini Enterprise** (Google Cloud paid product): supported via custom MCP server data stores.
- **Gemini web app** (`gemini.google.com`) / Gemini mobile app: **not yet supported** by Google's regular Gemini app. Track [this issue](https://support.google.com/gemini/thread/409485795/) — Google is rolling MCP support out gradually.

### Hermes (NousResearch)

Self-hosted autonomous agent across Telegram, Discord, Slack, WhatsApp, Signal, SMS, etc. Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  lifenote:
    url: "https://mcp.mylifenote.ai/mcp"
    auth: oauth
```

Then `/reload-mcp` inside any Hermes session. Full guide: [docs/HERMES.md](docs/HERMES.md).

### OpenClaw

Self-hosted personal AI assistant ("the lobster way"). One-liner:

```bash
openclaw mcp set lifenote '{"url":"https://mcp.mylifenote.ai/mcp","transport":"streamable-http"}'
openclaw doctor --fix
```

Full guide (including OAuth bridge for desktop and bearer-token for headless): [docs/OPENCLAW.md](docs/OPENCLAW.md).

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

All read-only, scoped to your account by two permissions:

**journal:read** unlocks:
- Your written journal entries (with AI-generated analysis: feelings, topics, people, themes)
- Your **Wisdom** collection — passages you highlighted from mentor responses
- Your **Practices** (continuous goals) and **Quests** (deadline goals) — with streaks, subgoals, and the AI-distilled context (the practice, the wisdom anchoring it, the mentor message)
- Your **Life Goal** — your singular ultimate aim
- Your **Yearly Goal** — your chosen Theme + description for each year
- Journal entries you've explicitly linked to a specific practice or quest

**chat:read** unlocks:
- Your past conversations with AI mentors (Marcus Aurelius, Naval, your Inner Wisdom, etc.)
- The full message thread of any conversation you point to

**What it can't do**:
- Write to your journal, change your settings, see payment info, or access other users' data
- Cross-user data is structurally inaccessible — every query is scoped to your user ID

You can revoke any agent anytime at <https://www.mylifenote.ai/settings/agents>. Each connection has a separate revoke button.

---

## Tools your agent can call

Fourteen tools available via MCP, grouped by what they do:

**Journal — your writing**
- `search_entries(query, since?, limit?)` — keyword search across entries, mentor responses, and chats
- `list_recent_entries(since?, limit?)` — most recent entries with previews
- `get_entry(entry_id)` — full text + analysis + mentor responses

**Wisdom — passages you saved (UI: "All Wisdom")**
- `list_wisdom(mentor?, since?, limit?)` — your highlights, newest first
- `search_wisdom(query, limit?)` — search within saved wisdom

**Mentor wisdom — what mentors have said to you**
- `search_mentor_wisdom(query, mentor?, since?, limit?)` — across responses + chats, optionally filtered by mentor

**Mentor conversations**
- `list_conversations(since?, limit?)` — past chats (mentor name + title + summary)
- `get_conversation(conversation_id)` — full message thread

**Practices and Quests — what you're working on**
- `list_practices_and_quests(status?, kind?, since?, min_streak?, has_active_subgoals?, limit?)` — filter by active/completed, practice/quest, streak threshold, etc.
- `get_practice_or_quest(item_id)` — full goal + aligned_action context + subgoals + progress history + linked journal entries
- `list_entries_for_goal(item_id, since?, limit?)` — entries you tagged to this specific goal

**Life direction — singular self-statements**
- `get_life_goal()` — your singular ultimate Life Goal
- `get_yearly_goal(year?)` — chosen Theme + description (default: current year)
- `list_yearly_goals()` — all years' themes (see how focus has evolved)

When you connect through Claude Desktop or Claude Code, all of these become available automatically. When you connect through Claude.ai's web Connectors, you'll see them in the conversation's tool list.

---

## CLI command reference

```
lifenote auth login | logout | whoami | status
lifenote token create --name NAME [--expires 30d|90d|365d] [--save]
lifenote token list | revoke <id>
lifenote search <query> [--since 30d] [--limit 20] [--json]
lifenote entries [--since 7d] [--until DATE] [--limit 20] [--with-responses]
                 [--updated-since ISO] [--after-id N] [--all] [--json]
lifenote export [--since] [--until] [--format md|json|csv] [--include-analysis]
                [--include-mentors] [-o FILE]
lifenote sync <folder> [--full]
lifenote today | week
lifenote conversations list | show <id>
lifenote mcp                  # stdio MCP server entry point
lifenote skills install       # bundled Claude Code skill
lifenote version
```

---

## Configuration

Environment variables (all optional):

- `LIFENOTE_TOKEN` — a personal access token; bypasses the keychain (cron, CI, Docker). `LIFENOTE_API_TOKEN` still works.
- `LIFENOTE_BASE_URL` — point at staging / dev (default: `https://www.mylifenote.ai`)

---

## How this is different from "just an API"

| | "Search your journal" | **Life Note as memory layer** |
|---|---|---|
| What you ask | Specific queries | Conversational, contextual |
| What the agent knows about you | Nothing — you re-introduce yourself each session | Already knows your themes, your Life Goal, your saved wisdom |
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
