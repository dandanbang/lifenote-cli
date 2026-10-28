"""
lifenote CLI — typer entry point.

Commands:
  auth login | logout | whoami | status
  token create | list | revoke   # personal access tokens for cron / CI
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
from datetime import datetime, timezone

import httpx

from .api import APIError, Session, delete, get, post
from .auth import (
    clear_saved_pat, clear_token, device_login, get_session_token, save_pat,
    store_credentials, token_source,
)
from .config import (
    ENV_TOKEN_VAR, EXIT_AUTH, EXIT_NETWORK, EXIT_SERVER, EXIT_USAGE,
)
from .output import console, emit, err_console

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Bring your private journal into your AI agents.",
    rich_markup_mode="rich",
)

auth_app = typer.Typer(no_args_is_help=True, help="Sign in, sign out, who am I.")
conv_app = typer.Typer(no_args_is_help=True, help="Past mentor conversations.")
skills_app = typer.Typer(no_args_is_help=True, help="Bundled agent skills.")
token_app = typer.Typer(no_args_is_help=True,
                        help="Personal access tokens for unattended jobs (cron, CI).")
app.add_typer(auth_app, name="auth")
app.add_typer(token_app, name="token")
app.add_typer(conv_app, name="conversations")
app.add_typer(skills_app, name="skills")


AUTH_HELP = (f"Run `lifenote auth login`, or set {ENV_TOKEN_VAR} to a fresh token "
             "(`lifenote token create`).")


def _fail(code: int, message: str):
    """One human line on stderr, then a documented exit code."""
    err_console.print(message, highlight=False, soft_wrap=True)
    raise typer.Exit(code)


def _detail(body) -> str:
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("reason") or body.get("error") or body)
    return str(body)[:200]


def _handle_api_error(e: APIError) -> None:
    error = e.body.get("error") if isinstance(e.body, dict) else None
    if e.status == 401:
        _fail(EXIT_AUTH, f"[red]Your Life Note token is expired, revoked, or invalid.[/] {AUTH_HELP}")
    if e.status == 403 and error == "pat_cannot_manage_tokens":
        _fail(EXIT_AUTH, "[red]A personal access token cannot manage tokens.[/] "
                         "Run `lifenote auth login` on this machine first.")
    if e.status == 403:
        _fail(EXIT_AUTH, f"[red]This token is not allowed to do that:[/] {_detail(e.body)}")
    if e.status == 429:
        _fail(EXIT_SERVER, f"[yellow]Rate limited by Life Note:[/] {_detail(e.body)}. Try again later.")
    if e.status in (400, 404, 409, 422):
        _fail(EXIT_USAGE, f"[red]Life Note rejected the request:[/] {_detail(e.body)}")
    _fail(EXIT_SERVER, f"[red]Life Note server error {e.status}.[/] Try again in a few minutes.")


def _require_token() -> None:
    if not token_source()[0]:
        _fail(EXIT_AUTH, f"[red]Not signed in.[/] {AUTH_HELP}")


def main():
    """Console entry point: maps network failures to their exit code."""
    try:
        app()
    except httpx.TransportError as e:
        err_console.print(f"[red]Can't reach Life Note[/] ({type(e).__name__}). "
                          "Check your connection and try again.", highlight=False)
        sys.exit(EXIT_NETWORK)


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
        _fail(EXIT_AUTH, f"[red]Login failed:[/] {e}")
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
    """Forget the stored sign-in and saved token (does not revoke them server-side)."""
    cleared = clear_token()
    cleared = clear_saved_pat() or cleared
    if cleared:
        console.print("[green]Signed out.[/] To revoke server-side, use `lifenote token revoke` "
                      "or Settings → Connected Agents.")
    else:
        console.print("[dim]No stored token.[/]")


@auth_app.command("whoami")
def auth_whoami(json: bool = typer.Option(False, "--json")):
    """Show who you're signed in as."""
    _require_token()
    try:
        emit(get("/api/agent/v1/whoami"), json)
    except APIError as e:
        _handle_api_error(e)


def _days_left(expires_at: str | None) -> int | None:
    if not expires_at:
        return None
    try:
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return (exp - datetime.now(timezone.utc)).days


@auth_app.command("status")
def auth_status(json: bool = typer.Option(False, "--json")):
    """Check the token this machine would use: where it comes from, whose it is, when it expires.

    Exit 0 if it works, 3 if missing/expired/revoked, 4 if Life Note can't be reached.
    """
    token, source = token_source()
    if not token:
        _fail(EXIT_AUTH, f"[red]Not signed in.[/] {AUTH_HELP}")
    try:
        who = get("/api/agent/v1/whoami")
    except APIError as e:
        _handle_api_error(e)
    status = {
        "ok": True,
        "source": source,
        "email": who.get("email"),
        "token_name": who.get("token_name"),
        "token_kind": who.get("token_kind"),
        "scopes": who.get("scopes"),
        "expires_at": who.get("expires_at"),
    }
    if json:
        emit(status, True)
        return
    kind = "personal access token" if who.get("token_kind") == "personal_access_token" else "sign-in"
    console.print(f"[green]OK[/] {who.get('email')} · {kind} [bold]{who.get('token_name')}[/] · from {source}",
                  highlight=False, soft_wrap=True)
    if who.get("token_kind") == "personal_access_token":
        days = _days_left(who.get("expires_at"))
        if days is not None:
            colour = "yellow" if days < 14 else "dim"
            console.print(f"[{colour}]Expires {who['expires_at'][:10]} ({days} days left).[/]")
    console.print(f"[dim]Scopes: {', '.join(who.get('scopes') or [])}[/]")


# ---------------------------------------------------------------------------
# token — personal access tokens
# ---------------------------------------------------------------------------

def _session_or_fail() -> str:
    token = get_session_token()
    if not token:
        _fail(EXIT_AUTH, "[red]Token commands need an interactive sign-in on this machine.[/] "
                         "Run `lifenote auth login` first.")
    return token


@token_app.command("create")
def token_create(
    name: str = typer.Option(..., "--name", help="What it's for, e.g. 'weekly obsidian sync'."),
    expires: str = typer.Option("90d", "--expires", help="30d, 90d, or 365d."),
    save: bool = typer.Option(False, "--save",
                              help="Also store it in this machine's keychain as the default token."),
    json: bool = typer.Option(False, "--json"),
):
    """Create a read-only personal access token. It is shown ONCE."""
    if expires not in ("30d", "90d", "365d"):
        _fail(EXIT_USAGE, "[red]--expires must be 30d, 90d, or 365d.[/]")
    session = _session_or_fail()
    try:
        created = post("/api/agent/v1/tokens",
                       {"name": name, "expires_in_days": int(expires[:-1])}, token=session)
    except APIError as e:
        _handle_api_error(e)
    if save:
        save_pat(created["token"])
    if json:
        emit(created, True)
        return
    console.print(f"[green]Created[/] token [bold]{created['name']}[/] (id {created['id']}), "
                  f"read-only, expires {created['expires_at'][:10]}.", highlight=False)
    console.print("\nCopy it now; it will not be shown again:\n")
    print(created["token"])
    console.print(f"\nFor cron / CI:  export {ENV_TOKEN_VAR}=<the token above>", highlight=False)
    if save:
        console.print("[dim]Saved to this machine's keychain as the default token.[/]")


@token_app.command("list")
def token_list(json: bool = typer.Option(False, "--json")):
    """Your personal access tokens: name, last used, expiry, status."""
    session = _session_or_fail()
    try:
        body = get_with(session, "/api/agent/v1/tokens")
    except APIError as e:
        _handle_api_error(e)
    emit(body, json)


@token_app.command("revoke")
def token_revoke(token_id: int = typer.Argument(..., help="The id from `lifenote token list`.")):
    """Revoke a personal access token. Anything using it stops working at once."""
    session = _session_or_fail()
    try:
        delete(f"/api/agent/v1/tokens/{token_id}", token=session)
    except APIError as e:
        _handle_api_error(e)
    console.print(f"[green]Revoked[/] token {token_id}.")


def get_with(token: str, path: str, params: dict | None = None) -> dict:
    with Session(token=token) as s:
        return s.get(path, params=params)


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
        help="Only entries written or edited since this ISO time "
             "(e.g. 2026-10-20T00:00:00Z), plus their same-day entries. "
             "Oldest change first. Add --reply-after-id to catch new mentor replies."),
    after_id: int | None = typer.Option(
        None, "--after-id", help="Only entries with a higher id. Lowest id first."),
    reply_after_id: int | None = typer.Option(
        None, "--reply-after-id",
        help="Also entries that got a mentor reply newer than this reply id "
             "(the `reply_cursor` from a previous --json run)."),
    all_pages: bool = typer.Option(False, "--all", help="Fetch every page, not just one."),
    json: bool = typer.Option(False, "--json"),
):
    """List journal entries.

    For incremental pulls, --json output carries `as_of` and `reply_cursor`:
    pass them as --updated-since and --reply-after-id next time.
    """
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
    if reply_after_id is not None:
        params["reply_after_id"] = reply_after_id
    try:
        with Session() as s:
            if all_pages:
                meta: dict = {}
                rows = list(s.iter_entries(params, page_size=max(1, min(100, limit)), meta=meta))
                payload = {"entries": rows, "count": len(rows), "as_of": meta.get("as_of"),
                           "reply_cursor": meta.get("reply_cursor")}
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
        _fail(EXIT_USAGE, f"[red]Unknown --format {fmt!r}.[/] Use md, json, or csv.")
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
    if stats["skipped"]:
        console.print(f"[yellow]Skipped {stats['skipped']} entries that arrived incomplete; "
                      "the next run retries them.[/]")


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
    if not token_source()[0]:
        # MCP clients see stderr in their logs
        sys.stderr.write("lifenote: not signed in. Run `lifenote auth login` first.\n")
        sys.exit(EXIT_AUTH)
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
    main()
