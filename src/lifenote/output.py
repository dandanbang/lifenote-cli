"""Rendering: human-readable for the terminal, --json for piping into agents."""
import json as _json

from rich.console import Console
from rich.table import Table

console = Console()


def emit(payload, json_mode: bool):
    if json_mode:
        # Stable, agent-pipe-friendly JSON (no rich formatting)
        print(_json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))
        return
    # Otherwise dispatch by shape
    if isinstance(payload, dict) and "entries" in payload:
        _print_entries(payload)
    elif isinstance(payload, dict) and "results" in payload:
        _print_search(payload)
    elif isinstance(payload, dict) and "conversations" in payload:
        _print_conversations(payload)
    elif isinstance(payload, dict) and "messages" in payload:
        _print_conversation(payload)
    elif isinstance(payload, dict) and "tokens" in payload:
        _print_tokens(payload)
    else:
        console.print(payload)


def _print_entries(p):
    if p.get("count", 0) == 0:
        console.print("[dim]No entries.[/]")
        return
    for e in p["entries"]:
        head = f"[bold]{e['date']}[/]"
        if e.get("emoji"):
            head += f" {e['emoji']}"
        console.print(head)
        if e.get("preview"):
            console.print(f"  [dim]{e['preview']}[/]")
        console.print()


def _print_search(p):
    console.print(f"[dim]{p['count']} hits for[/] [bold]{p['query']}[/] "
                  f"[dim](scanned {p['scanned']})[/]\n")
    if not p["results"]:
        console.print("[dim]No matches.[/]")
        return
    for r in p["results"]:
        tag = r["source"].replace("_", " ")
        date = r.get("date") or ""
        console.print(f"[bold cyan]{tag}[/] [dim]{date}[/]")
        console.print(f"  {r['snippet']}")
        console.print()


def _print_conversations(p):
    if p.get("count", 0) == 0:
        console.print("[dim]No conversations.[/]")
        return
    t = Table(show_header=True, header_style="bold", box=None)
    t.add_column("ID")
    t.add_column("Mentor")
    t.add_column("Last")
    t.add_column("Title")
    for c in p["conversations"]:
        t.add_row(str(c["id"]), c.get("mentor") or "-",
                  (c.get("last_message_at") or "")[:10],
                  (c.get("title") or "(no title)")[:60])
    console.print(t)


def _print_conversation(p):
    console.print(f"[bold]{p.get('mentor') or 'Conversation'}[/] — {p.get('title') or ''}")
    console.print()
    for m in p["messages"]:
        who = "[cyan]you[/]" if m["sender"] == "user" else f"[magenta]{p.get('mentor','mentor')}[/]"
        console.print(f"{who} [dim]{(m.get('timestamp') or '')[:16]}[/]")
        console.print(f"  {m.get('content') or '[dim](no content)[/]'}")
        console.print()


def _print_tokens(p):
    t = Table(show_header=True, header_style="bold", box=None)
    t.add_column("ID")
    t.add_column("Name")
    t.add_column("Kind")
    t.add_column("Last used")
    t.add_column("Status")
    for tok in p["tokens"]:
        t.add_row(
            str(tok["id"]), tok["name"], tok["client_kind"],
            (tok.get("last_used_at") or "never")[:16],
            "[green]active[/]" if tok["active"] else "[red]revoked[/]",
        )
    console.print(t)
