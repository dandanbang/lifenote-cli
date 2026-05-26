# Life Note + OpenClaw

Connect [OpenClaw](https://github.com/openclaw/openclaw) — the self-hosted personal AI assistant — to your Life Note journal. Once wired up, OpenClaw can reach into your past entries, saved wisdom, mentor conversations, and life goals from any messaging app you've connected (WhatsApp, Telegram, Slack, Signal, iMessage, Discord, etc.) and from the Claude Code sessions it spawns.

## What you need

- OpenClaw installed and running ([OpenClaw install guide](https://docs.openclaw.ai/))
- A Life Note account ([sign up](https://www.mylifenote.ai))

You do **not** need to install the `lifenote` CLI — OpenClaw talks to Life Note's hosted MCP server directly. The CLI is only needed if you also want terminal access.

## Configure (one-liner)

The fastest path is the OpenClaw CLI:

```bash
openclaw mcp set lifenote '{
  "url": "https://mcp.mylifenote.ai/mcp",
  "transport": "streamable-http"
}'
```

Then verify:

```bash
openclaw mcp list
openclaw doctor --fix
```

You should see `lifenote` listed with 14 tools.

## Configure (manually)

If you'd rather edit the config file, open `~/.openclaw/openclaw.json` and add Life Note under `mcp.servers`:

```json
{
  "mcp": {
    "servers": {
      "lifenote": {
        "url": "https://mcp.mylifenote.ai/mcp",
        "transport": "streamable-http"
      }
    }
  }
}
```

Then run `openclaw doctor --fix` to normalize and reload.

## Authentication

Life Note uses OAuth 2.1 + PKCE. There are two paths:

**OAuth bridge (recommended for desktop / personal use).** Use the community-maintained [openclaw-mcp OAuth bridge](https://github.com/freema/openclaw-mcp) — it handles the OAuth handshake transparently and works well with OpenClaw's gateway model.

**Personal access token (recommended for headless / server deployments).** Generate one at [Settings → Connected Agents](https://www.mylifenote.ai/settings/agents) and add it as a header:

```json
{
  "mcp": {
    "servers": {
      "lifenote": {
        "url": "https://mcp.mylifenote.ai/mcp",
        "transport": "streamable-http",
        "headers": {
          "Authorization": "Bearer YOUR_TOKEN"
        }
      }
    }
  }
}
```

## What this unlocks

From any messaging app OpenClaw is listening on, you can now ask things like:

> *"What have I been writing about my cofounder this month?"*
> *"What did Marcus Aurelius say to me about anxiety?"*
> *"What's my Life Goal, and what practices am I doing toward it?"*

OpenClaw will figure out which Life Note tool to call — and if it spawns a Claude Code session for a deeper task, those sessions inherit the same MCP connection.

See the [main README](../README.md#what-an-agent-can-read) for the full tool list and the scopes (`journal:read`, `chat:read`) you'll be granting.

## Revoke

Disconnect OpenClaw from Life Note any time at [Settings → Connected Agents](https://www.mylifenote.ai/settings/agents). One-click revoke per connection.
