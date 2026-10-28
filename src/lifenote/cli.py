"""
lifenote CLI — typer entry point.

Commands:
  auth login | logout | whoami
  search <query>
  entries [--since] [--until] [--limit] [--with-responses]
          [--updated-since] [--after-id] [--all]
  export [--since] [--until] [--format md|json|csv] [--include-analysis]
         [--include-mentors] [--output]
  sync <folder> [--full]
  today | week
  conversations list | show <id>
  mcp                 # stdio MCP server
  skills install      # bundled Claude Code skill
"""
import sys
from pathlib import Path

import typer

from . import __version__
from .api import APIError, Session, get
from .auth import device_login, store_credentials, clear_token, get_token
from .output import console, emit

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Bring your private journal into your AI agents.",
    rich_markup_mode="rich",
)

auth_app = typer.Typer(no_args_is_help=True, help="Sign in, sign out, who am I.")
conv_app = typer.Typer(no_args_is_help=True, help="Past mentor conversations.")
skills_app = typer.Typer(no_args_is_help=True, help="Bundled agent skills.")
app.add_typer(auth_app, name="auth")
app.add_typer(conv_app, name="conversations")
app.add_typer(skills_app, name="skills")


def _handle_api_error(e: APIError) -> None:
    if e.status == 401:
        console.print("[red]Not signed in.[/] Run [bold]lifenote auth login[/].")
    elif e.status == 403:
        console.print(f"[red]Permission denied:[/] {e.body}")
    elif e.status == 429:
        console.print(f"[yellow]Rate limited:[/] {e.body}")
    else:
        console.print(f"[red]API error {e.status}:[/] {e.body}")
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

@auth_app.command("login")
def auth_login(
    name: str | None = typer.Option(None, help="Name shown in the approval UI."),
    no_browser: bool = typer.Option(False, help="Don't open the browser automatically."),
):
    """Sign in via the device flow."""
    try:
        result = device_login(name=name, open_browser=not no_browser)
    except RuntimeError as e:
        console.print(f"[red]Login failed:[/] {e}")
        raise typer.Exit(1)
    # Store full credentials so the CLI can transparently refresh when the
    # 1-hour access token nears expiry. (Codex P2 #5)
    store_credentials(
        access=result["access_token"],
        refresh=result.get("refresh_token"),
        expires_in=result.get("expires_in"),
    )
    console.print(f"[green]Signed in.[/] Scopes: {result.get('scope', '?')}")


@auth_app.command("logout")
def auth_logout():
    """Forget the stored token (does not revoke it server-side)."""
    if clear_token():
        console.print("[green]Signed out.[/] To revoke server-side, visit Settings → Connected Agents.")
    else:
        console.print("[dim]No stored token.[/]")


@auth_app.command("whoami")
def auth_whoami(json: bool = typer.Option(False, "--json")):
    """Show who you're signed in as."""
    if not get_token():
        console.print("[red]Not signed in.[/] Run [bold]lifenote auth login[/].")
        raise typer.Exit(1)
    try:
        emit(get("/api/agent/v1/whoami"), json)
    except APIError as e:
        _handle_api_error(e)


# ---------------------------------------------------------------------------
# search / entries
# ---------------------------------------------------------------------------

@app.command()
def search(
    query: str = typer.Argument(..., help="Search term (≥2 chars)."),
    since: str | None = typer.Option(None, help="Time bound: 7d / 30d / YYYY-MM-DD"),
    limit: int = typer.Option(20, help="Max results (1–50)."),
    json: bool = typer.Option(False, "--json"),
):
    """Search journal entries, mentor responses, and conversations."""
    params = {"q": query, "limit": limit}
    if since:
        params["since"] = since
    try:
        emit(get("/api/agent/v1/search", params=params), json)
    except APIError as e:
        _handle_api_error(e)


@app.command()
def entries(
    since: str | None = typer.Option(None, help="Entry date from: 7d / 30d / YYYY-MM-DD"),
    until: str | None = typer.Option(None, help="Entry date up to (inclusive): YYYY-MM-DD"),
    limit: int = typer.Option(20, help="Max entries per page (1–100)."),
    with_responses: bool = typer.Option(
        False, "--with-responses",
        help="Add Daily Insights (analysis) and mentor replies to each entry."),
    updated_since: str | None = typer.Option(
        None, "--updated-since",
        help="Only entries written, edited, or given a new mentor reply since "
             "this ISO time (e.g. 2026-10-20T00:00:00Z). Oldest change first."),
    after_id: int | None = typer.Option(
        None, "--after-id", help="Only entries with a higher id. Lowest id first."),
    all_pages: bool = typer.Option(False, "--all", help="Fetch every page, not just one."),
    json: bool = typer.Option(False, "--json"),
):
    """List journal entries. --json output carries `as_of`: pass it as --updated-since next time."""
    params: dict = {"limit": limit}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    if with_responses:
        params["with_responses"] = 1
    if updated_since:
        params["updated_since"] = updated_since
    if after_id is not None:
        params["after_id"] = after_id
    try:
        with Session() as s:
            if all_pages:
                meta: dict = {}
                rows = list(s.iter_entries(params, page_size=max(1, min(100, limit)), meta=meta))
                payload = {"entries": rows, "count": len(rows), "as_of": meta.get("as_of")}
            else:
                payload = s.get("/api/agent/v1/entries", params=params)
        emit(payload, json)
    except APIError as e:
        _handle_api_error(e)


@app.command()
def export(
    since: str | None = typer.Option(None, help="Entry date from: 7d / 30d / YYYY-MM-DD"),
    until: str | None = typer.Option(None, help="Entry date up to (inclusive): YYYY-MM-DD"),
    fmt: str = typer.Option("md", "--format", help="md | json | csv"),
    include_analysis: bool = typer.Option(False, "--include-analysis",
                                          help="Include Daily Insights."),
    include_mentors: bool = typer.Option(False, "--include-mentors",
                                         help="Include mentor replies."),
    output: Path | None = typer.Option(None, "--output", "-o",
                                       help="Write to this file instead of stdout."),
):
    """Export entries (oldest first) as Markdown, JSON, or CSV."""
    from .render import export_csv, export_json, export_md
    renderers = {"md": export_md, "json": export_json, "csv": export_csv}
    if fmt not in renderers:
        console.print(f"[red]Unknown --format {fmt!r}.[/] Use md, json, or csv.")
        raise typer.Exit(2)
    params: dict = {}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    if include_analysis or include_mentors:
        params["with_responses"] = 1
    try:
        with Session() as s:
            rows = list(s.iter_entries(params))
    except APIError as e:
        _handle_api_error(e)
    rows.sort(key=lambda e: (str(e.get("date") or ""), e.get("id") or 0))
    text = renderers[fmt](rows, include_analysis=include_analysis,
                          include_mentors=include_mentors)
    if output:
        output.expanduser().write_text(text, encoding="utf-8")
        console.print(f"[green]Exported[/] {len(rows)} entries → {output}",
                      highlight=False, soft_wrap=True)
    else:
        sys.stdout.write(text)


@app.command()
def sync(
    folder: Path = typer.Argument(..., help="Folder to keep in sync, e.g. your Obsidian vault's 'Life Note' folder."),
    full: bool = typer.Option(False, "--full", help="Re-pull every entry, ignoring the saved cursor."),
):
    """Mirror your journal into FOLDER: one Markdown note per entry, with mentor replies.

    Safe to run on a schedule: only changed notes are rewritten, and anything
    you write below a note's "your notes" line is kept.
    """
    from .sync import sync as run_sync
    try:
        with Session() as s:
            stats = run_sync(folder, s, full=full)
    except APIError as e:
        _handle_api_error(e)
    console.print(
        f"[green]Synced[/] {stats['new']} new, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged → {folder}", highlight=False, soft_wrap=True)


@app.command()
def today(json: bool = typer.Option(False, "--json")):
    """Today's journal entries (shortcut for entries --since 1d)."""
    try:
        emit(get("/api/agent/v1/entries", params={"since": "1d", "limit": 50}), json)
    except APIError as e:
        _handle_api_error(e)


@app.command()
def week(json: bool = typer.Option(False, "--json")):
    """The last 7 days of entries."""
    try:
        emit(get("/api/agent/v1/entries", params={"since": "7d", "limit": 100}), json)
    except APIError as e:
        _handle_api_error(e)


# ---------------------------------------------------------------------------
# conversations
# ---------------------------------------------------------------------------

@conv_app.command("list")
def conv_list(
    since: str | None = typer.Option(None),
    limit: int = typer.Option(20),
    json: bool = typer.Option(False, "--json"),
):
    """List past mentor conversations."""
    params: dict = {"limit": limit}
    if since:
        params["since"] = since
    try:
        emit(get("/api/agent/v1/conversations", params=params), json)
    except APIError as e:
        _handle_api_error(e)


@conv_app.command("show")
def conv_show(
    conversation_id: int = typer.Argument(...),
    json: bool = typer.Option(False, "--json"),
):
    """Show one conversation's full message thread."""
    try:
        emit(get(f"/api/agent/v1/conversations/{conversation_id}"), json)
    except APIError as e:
        _handle_api_error(e)


# ---------------------------------------------------------------------------
# mcp — stdio MCP server proxying to the HTTP MCP endpoint
# ---------------------------------------------------------------------------

@app.command()
def mcp():
    """
    Run as a stdio MCP server. Reads JSON-RPC from stdin, writes to stdout.
    Proxies every request to /api/agent/v1/mcp using the stored token.

    Configure in Claude Desktop's claude_desktop_config.json:
      { "mcpServers": { "lifenote": { "command": "lifenote", "args": ["mcp"] } } }
    """
    from .mcp_proxy import run as run_mcp
    if not get_token():
        # MCP clients see stderr in their logs
        sys.stderr.write("lifenote: not signed in. Run `lifenote auth login` first.\n")
        sys.exit(1)
    run_mcp()


# ---------------------------------------------------------------------------
# skills install
# ---------------------------------------------------------------------------

@skills_app.command("install")
def skills_install(
    target: str = typer.Option(
        "~/.claude/skills",
        help="Where to drop the lifenote.md skill.",
    ),
):
    """Install the bundled Claude Code skill into ~/.claude/skills/."""
    from .skill import install as install_skill
    path = install_skill(target)
    console.print(f"[green]Installed[/] {path}")


@app.command()
def version():
    """Print the CLI version."""
    console.print(f"lifenote {__version__}")


if __name__ == "__main__":
    app()
