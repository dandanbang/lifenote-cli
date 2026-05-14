"""
stdio MCP server that proxies to the HTTP MCP endpoint.

Reads JSON-RPC requests from stdin (one per line), forwards each to
POST /api/agent/v1/mcp with the user's Bearer token, writes the response
back to stdout. Lives as `lifenote mcp` so MCP clients (Claude Desktop,
Cursor) can spawn the binary without dealing with HTTP+auth themselves.

Long-running correctness (Codex round 2 P2 #6 + #7):
  - 202 No Content → notification; emit nothing per JSON-RPC spec
  - 401 → refresh access token from keyring (refresh path) and retry once;
    if refresh fails, emit JSON-RPC error and ask user to re-login
  - The proxy holds a single session id across requests
"""
import json
import sys

import httpx

from .auth import get_token, _try_refresh, _read_keyring_blob
from .config import base_url


def run() -> None:
    if not get_token():
        sys.stderr.write("lifenote mcp: no token. Run `lifenote auth login` first.\n")
        sys.exit(1)

    session_id: str | None = None
    url = f"{base_url()}/api/agent/v1/mcp"

    def headers_with_token() -> dict:
        return {
            "Authorization": f"Bearer {get_token() or ''}",
            "Content-Type": "application/json",
            "User-Agent": "lifenote-cli/0.1.1 (mcp_proxy)",
        }

    def post_once(line: str, sid: str | None) -> httpx.Response:
        h = headers_with_token()
        if sid:
            h["Mcp-Session-Id"] = sid
        return _http_client.post(url, headers=h, content=line)

    def refresh_or_die() -> bool:
        blob = _read_keyring_blob()
        if not blob or not blob.get('refresh'):
            return False
        return _try_refresh(blob['refresh']) is not None

    with httpx.Client(timeout=120.0) as _http_client:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                _emit({"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32700, "message": "Parse error"}})
                continue

            try:
                r = post_once(line, session_id)
                # 401 → token expired; refresh once and retry
                if r.status_code == 401:
                    if refresh_or_die():
                        # Session may have been bound to the old token; drop it
                        # so we re-initialize cleanly.
                        session_id = None
                        r = post_once(line, None)
                    else:
                        _emit({"jsonrpc": "2.0", "id": req.get("id"),
                               "error": {"code": -32001,
                                         "message": "lifenote: token expired and refresh failed; run `lifenote auth login`"}})
                        continue
            except httpx.HTTPError as e:
                _emit({"jsonrpc": "2.0", "id": req.get("id"),
                       "error": {"code": -32603, "message": f"transport error: {e}"}})
                continue

            # Capture the session id on initialize so subsequent calls echo it
            if req.get("method") == "initialize":
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    session_id = sid

            # Notifications: server returns 202 No Content; spec says emit
            # nothing back to the MCP client (Codex round 2 P2 #6).
            if r.status_code == 202 or not r.content:
                continue

            try:
                _emit(r.json())
            except ValueError:
                _emit({"jsonrpc": "2.0", "id": req.get("id"),
                       "error": {"code": -32603,
                                 "message": f"server returned non-JSON: {r.text[:200]}"}})


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()
