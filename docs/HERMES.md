# Life Note + Hermes

Connect [Hermes](https://github.com/NousResearch/hermes-agent) — NousResearch's self-hosted autonomous agent — to your Life Note journal. Once wired up, Hermes can reach into your past entries, saved wisdom, conversations with mentors, and life goals from any messaging gateway (Telegram, Discord, Slack, WhatsApp, Signal, SMS, etc.) that you've connected to Hermes.

## What you need

- Hermes installed and running ([Hermes install guide](https://hermes-agent.nousresearch.com/docs/))
- A Life Note account ([sign up](https://www.mylifenote.ai))

You do **not** need to install the `lifenote` CLI for this — Hermes talks to Life Note's hosted MCP server directly over HTTP. The CLI is only needed if you also want terminal access.

## Configure

Edit `~/.hermes/config.yaml` and add Life Note under `mcp_servers`:

```yaml
mcp_servers:
  lifenote:
    url: "https://mcp.mylifenote.ai/mcp"
    auth: oauth
```

`auth: oauth` tells Hermes to do the OAuth 2.1 + PKCE handshake with Life Note — it will open a browser the first time, you approve the connection, and Hermes stores the refresh token from then on. No manual token copy-paste.

If you prefer static tokens (e.g. running Hermes in a headless container), generate a personal access token in [Settings → Connected Agents](https://www.mylifenote.ai/settings/agents) and use:

```yaml
mcp_servers:
  lifenote:
    url: "https://mcp.mylifenote.ai/mcp"
    headers:
      Authorization: "Bearer YOUR_TOKEN"
```

## Reload

Inside any Hermes session, run:

```
/reload-mcp
```

Then verify with:

```
hermes mcp available
```

You should see `lifenote` listed with 14 tools.

## What this unlocks

From any gateway Hermes is listening on, you can now ask things like:

> *"What have I been writing about my cofounder this month?"*
> *"What did Marcus Aurelius say to me about anxiety?"*
> *"What's my Life Goal, and what practices am I doing toward it?"*

Hermes will figure out which Life Note tool to call. You just ask.

See the [main README](../README.md#what-an-agent-can-read) for the full list of tools and the scopes (`journal:read`, `chat:read`) you'll be granting.

## Revoke

Disconnect Hermes from Life Note any time at [Settings → Connected Agents](https://www.mylifenote.ai/settings/agents). One-click revoke per connection.
