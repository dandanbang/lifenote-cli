"""stdio MCP proxy for the HTTP endpoint, with one sign-in refresh on 401.

Only requests receive replies; notifications never produce stdout responses.
HTTP/transport failures and invalid upstream responses become correlated errors.
"""
import json
import sys

import httpx

from .auth import token_source, _refresh_with_lock, _read_keyring_blob
from .api import USER_AGENT
from .config import base_url


def _auth_error(source: str | None) -> str:
    if source == "keychain (personal access token)":
        return ("lifenote: saved personal access token was refused (expired or revoked); "
                "run `lifenote token create --name mcp --save` to replace it or "
                "`lifenote auth logout` to remove saved credentials")
    if source and source.startswith("env "):
        return f"lifenote: token from {source} was refused; replace or unset that environment variable"
    return ("lifenote: sign-in token was refused and refresh did not restore access; "
            "retry later or run `lifenote auth login`")


def _valid_response(body, req_id) -> bool:
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return False
    if "id" not in body or type(body["id"]) is not type(req_id) or body["id"] != req_id:
        return False
    if ("result" in body) == ("error" in body):
        return False
    if "error" in body:
        error = body["error"]
        return (isinstance(error, dict) and type(error.get("code")) is int
                and isinstance(error.get("message"), str))
    return True


def run() -> None:
    if not token_source()[0]:
        sys.stderr.write("lifenote mcp: no token. Run `lifenote auth login` first.\n")
        sys.exit(1)

    session_id: str | None = None
    url = f"{base_url()}/api/agent/v1/mcp"

    def post_once(line: str, sid: str | None, token: str | None) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token or ''}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER_AGENT} (mcp_proxy)",
        }
        if sid:
            headers["Mcp-Session-Id"] = sid
        return client.post(url, headers=headers, content=line)

    def refresh(source: str | None) -> str | None:
        # Refresh only the credential actually sent, never a lower-priority
        # sign-in hidden by a PAT. Keep the cross-process rotation lock.
        if source != "keychain (sign-in)":
            return None
        blob = _read_keyring_blob()
        if not blob or not blob.get('refresh'):
            return None
        return _refresh_with_lock(blob['refresh'])

    with httpx.Client(timeout=120.0) as client:
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
            if not isinstance(req, dict):
                _emit({"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32600, "message": "Invalid Request"}})
                continue

            def fail(code: int, message: str) -> None:
                if "id" in req:
                    _emit({"jsonrpc": "2.0", "id": req["id"],
                           "error": {"code": code, "message": message}})

            token, source = token_source()
            try:
                r = post_once(line, session_id, token)
                if r.status_code == 401:
                    rotated = refresh(source)
                    if rotated:
                        # A session may be bound to the old access token.
                        session_id = None
                        r = post_once(line, None, rotated)
                    if r.status_code == 401:
                        fail(-32001, _auth_error(source))
                        continue
            except httpx.HTTPError:
                fail(-32603, "lifenote: transport error contacting MCP server")
                continue

            # Notifications must not receive replies, even on auth/HTTP errors.
            if "id" not in req:
                continue
            if not 200 <= r.status_code < 300:
                fail(-32603, f"lifenote: HTTP {r.status_code} from MCP server")
                continue
            try:
                body = r.json()
            except ValueError:
                body = None
            if not _valid_response(body, req["id"]):
                fail(-32603, "lifenote: server returned an invalid JSON-RPC response")
                continue

            if req.get("method") == "initialize" and "result" in body:
                sid = r.headers.get("Mcp-Session-Id")
                if sid:
                    session_id = sid
            _emit(body)


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()
