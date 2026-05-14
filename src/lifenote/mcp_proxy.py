"""
stdio MCP server that proxies to the HTTP MCP endpoint.

Reads JSON-RPC requests from stdin (one per line), forwards each to
POST /api/agent/v1/mcp with the user's Bearer token, writes the response
back to stdout. Lives as `lifenote mcp` so MCP clients (Claude Desktop,
Cursor) can spawn the binary without dealing with HTTP+auth themselves.
"""
import json
import sys

import httpx

from .auth import get_token
from .config import base_url


def run() -> None:
    token = get_token()
    if not token:
        sys.stderr.write("lifenote mcp: no token. Run `lifenote auth login` first.\n")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "lifenote-cli/0.1.0 (mcp_proxy)",
    }
    session_id: str | None = None
    url = f"{base_url()}/api/agent/v1/mcp"

    with httpx.Client(timeout=120.0) as client:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                # Malformed input — emit a JSON-RPC parse error and continue
                _emit({"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32700, "message": "Parse error"}})
                continue

            req_headers = dict(headers)
            if session_id:
                req_headers["Mcp-Session-Id"] = session_id

            try:
                r = client.post(url, headers=req_headers, content=line)
            except httpx.HTTPError as e:
                _emit({"jsonrpc": "2.0", "id": req.get("id"),
                       "error": {"code": -32603, "message": f"transport error: {e}"}})
                continue

            # Capture the session id on initialize so subsequent calls echo it
            if req.get("method") == "initialize":
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    session_id = sid

            try:
                _emit(r.json())
            except ValueError:
                _emit({"jsonrpc": "2.0", "id": req.get("id"),
                       "error": {"code": -32603, "message": f"server returned non-JSON: {r.text[:200]}"}})


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()
