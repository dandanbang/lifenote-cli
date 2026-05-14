"""Bundled Claude Code skill — drops a markdown file into ~/.claude/skills/."""
import os

SKILL_NAME = "lifenote.md"

SKILL_BODY = """---
name: lifenote
description: |
  Use Life Note as the user's reflective memory layer. Search their journal
  entries, past mentor conversations, and emotional themes — to ground
  responses in who the user actually is, not what you'd guess.
---

# Life Note

The user keeps a private journal at https://www.mylifenote.ai. They've connected
it to you so you can read from it as part of your responses.

## When to reach for Life Note (proactively, without being asked)

- The user mentions a feeling ("I'm anxious about X", "I've been frustrated lately")
  → search the journal for that feeling word + topic
- The user references a person, project, or recurring theme by name
  → search for the name; if hits, read at least one entry
- The user asks "why am I…" or "what's been on my mind lately"
  → list recent entries (last 7 days)
- The user references "what [mentor] said" or any past mentor chat
  → list conversations and read the relevant one

## When NOT to reach for Life Note

- Coding / debugging questions
- General factual queries
- Anything where the user is acting in a professional or task-execution mode,
  not a reflective one

## How to use what you find

- **Paraphrase, don't quote verbatim.** The user wrote those words for themselves,
  not for you to recite back. Reference what they said in your own voice.
- **Cite the date casually**: "you wrote on Tuesday that you were…" — not
  "Per journal entry id 39938 dated 2026-05-06…"
- **If search returns nothing, say so plainly.** Don't fabricate continuity.
- **Don't summarize the whole journal.** Pull what's relevant to this exact
  moment in the conversation. The user has hundreds of entries.

## Boundaries

- You can READ. You cannot write to the journal in this version.
- The journal contains emotionally significant material. If recent entries
  reference self-harm, severe distress, or crisis, prioritize a caring,
  grounded response and the appropriate hotlines — don't analyze.

## Tools available (via the lifenote MCP server)

- `search_entries(query, since?, limit?)` — keyword search across entries
- `list_recent_entries(since?, limit?)` — most recent with previews
- `get_entry(entry_id)` — full text + analysis + mentor responses
- `list_conversations(since?, limit?)` — past mentor chats
- `get_conversation(conversation_id)` — full message thread
"""


def install(target_dir: str) -> str:
    target_dir = os.path.expanduser(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, SKILL_NAME)
    with open(path, "w", encoding="utf-8") as f:
        f.write(SKILL_BODY)
    return path
