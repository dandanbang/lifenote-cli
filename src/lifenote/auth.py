"""
Token storage + device-flow login + automatic refresh.

Storage precedence (read order):
  1. LIFENOTE_TOKEN env var (then the older LIFENOTE_API_TOKEN), for cron,
     CI, Docker and headless agents. Usually a personal access token.
  2. A personal access token saved with `lifenote token create --save`
     (OS keychain).
  3. The device-login session (OS keychain): a JSON blob with
     {access, refresh, expires_at} so the CLI can transparently refresh
     access tokens before they expire (Codex P2 #5).

The env-var path is essential: keyring fails or is unavailable in many
headless environments (CI runners, Docker without secrets manager,
sandboxed agents), and on some headless Linux boxes a keyring lookup
blocks for ~25 s waiting on D-Bus. With the env var set, the keychain is
never touched. Env-var mode skips refresh: a PAT does not need one.
"""
import json
import os
import socket
import time
import webbrowser
from datetime import datetime, timedelta, timezone

import httpx

from .config import (
    ENV_TOKEN_VAR, ENV_TOKEN_VAR_LEGACY, KEYRING_PAT_USERNAME, KEYRING_SERVICE,
    KEYRING_USERNAME, base_url,
)

# Refresh access token when it has fewer than this many seconds left
REFRESH_LEEWAY_SECONDS = 120


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_keyring_blob() -> dict | None:
    try:
        import keyring
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None
    if not raw:
        return None
    try:
        blob = json.loads(raw)
        if isinstance(blob, dict) and 'access' in blob:
            return blob
        # Legacy: pre-refresh-rotation versions stored just the access token
        return {'access': raw, 'refresh': None, 'expires_at': None}
    except (ValueError, TypeError):
        return {'access': raw, 'refresh': None, 'expires_at': None}


def _write_keyring_blob(blob: dict) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, json.dumps(blob))


def store_credentials(access: str, refresh: str | None, expires_in: int | None) -> None:
    """Save access + refresh + computed absolute expiry."""
    expires_at = None
    if expires_in:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    _write_keyring_blob({'access': access, 'refresh': refresh, 'expires_at': expires_at})


def token_source() -> tuple[str | None, str | None]:
    """(token, where it came from) following the read order above."""
    for var in (ENV_TOKEN_VAR, ENV_TOKEN_VAR_LEGACY):
        env = (os.environ.get(var) or "").strip()
        if env:
            return env, f"env {var}"
    pat = get_saved_pat()
    if pat:
        return pat, "keychain (personal access token)"
    session = get_session_token()
    if session:
        return session, "keychain (sign-in)"
    return None, None


def get_token() -> str | None:
    """The token to send: env var, else saved PAT, else the sign-in session."""
    return token_source()[0]


def get_saved_pat() -> str | None:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_PAT_USERNAME) or None
    except Exception:
        return None


def save_pat(token: str) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, KEYRING_PAT_USERNAME, token)


def clear_saved_pat() -> bool:
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, KEYRING_PAT_USERNAME)
        return True
    except Exception:
        return False


def get_session_token() -> str | None:
    """
    The device-login session only (never an env var or a PAT): managing
    tokens needs it. If the keyring blob has a refresh token and the access
    is near expiry, transparently refreshes (with a cross-process file lock
    so two CLIs/MCP-proxies running concurrently don't both rotate the same
    refresh token and trigger family-burn — Codex round 3 P2 #4).

    Returns the access token or None.
    """
    blob = _read_keyring_blob()
    if not blob:
        return None
    access = blob.get('access')
    refresh = blob.get('refresh')
    expires_at = blob.get('expires_at')
    if access and refresh and expires_at and _is_near_expiry(expires_at):
        rotated = _refresh_with_lock(refresh)
        if rotated:
            return rotated
    return access


def _is_near_expiry(expires_at_iso: str) -> bool:
    try:
        exp = datetime.fromisoformat(expires_at_iso)
    except ValueError:
        return True
    return (exp - datetime.now(timezone.utc)).total_seconds() < REFRESH_LEEWAY_SECONDS


def _lock_path() -> str:
    """Per-user file lock for refresh — under XDG runtime dir if possible."""
    import tempfile
    base = os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir()
    return os.path.join(base, 'lifenote-cli-refresh.lock')


def _refresh_with_lock(refresh_plain: str) -> str | None:
    """
    Acquire a cross-platform file lock around the refresh exchange (filelock
    handles Windows, macOS, Linux). While holding the lock we re-read the
    keyring; if another process already rotated, return its newly-stored
    access without burning the family.

    Codex round 5 P3: fail closed if filelock is missing — racing refresh
    would burn the family on concurrent processes. filelock is a declared
    dependency, so missing it means a broken install; tell the user to
    reinstall rather than silently downgrading the guarantee.
    """
    try:
        from filelock import FileLock, Timeout
    except ImportError:
        import sys as _sys
        _sys.stderr.write(
            'lifenote: filelock dependency is missing — refresh would race '
            'across processes and burn your session. Reinstall the CLI '
            '(pipx reinstall lifenote) and try again.\n'
        )
        return None

    lock = FileLock(_lock_path() + '.flock', timeout=30)
    try:
        with lock:
            latest = _read_keyring_blob() or {}
            latest_refresh = latest.get('refresh')
            latest_access = latest.get('access')
            latest_expires = latest.get('expires_at')
            if latest_refresh != refresh_plain and latest_access and latest_expires:
                if not _is_near_expiry(latest_expires):
                    return latest_access  # someone else just refreshed — use it
            return _try_refresh(latest_refresh or refresh_plain)
    except Timeout:
        # Another process is taking too long; don't burn the family
        return None


def _try_refresh(refresh_plain: str) -> str | None:
    """
    Exchange refresh token for a new pair via /api/agent/v1/oauth/token.
    On reuse-detected (invalid_grant), clear stored creds — the user must
    re-login. Returns new access token on success, None on failure.

    Caller is responsible for serialization (use _refresh_with_lock above
    when running from a long-lived process like mcp_proxy).
    """
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f'{base_url()}/api/agent/v1/oauth/token',
                data={'grant_type': 'refresh_token', 'refresh_token': refresh_plain},
            )
        if r.status_code != 200:
            # invalid_grant could mean: expired, revoked, OR reuse detected
            # (family burned). In any case, the stored creds are dead.
            clear_token()
            return None
        body = r.json()
        store_credentials(
            access=body['access_token'],
            refresh=body.get('refresh_token'),
            expires_in=body.get('expires_in'),
        )
        return body['access_token']
    except Exception:
        return None


def set_token(token: str) -> None:
    """
    Legacy API — store just an access token (no refresh, no expiry). Kept
    for backward-compat with old-CLI users; new logins go through
    store_credentials() instead.
    """
    _write_keyring_blob({'access': token, 'refresh': None, 'expires_at': None})


def clear_token() -> bool:
    """Remove from keyring. Env var (if set) is left alone."""
    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Device flow
# ---------------------------------------------------------------------------

def _agent_name() -> str:
    """Friendly default name shown in the approval UI. User-overridable."""
    host = socket.gethostname().split(".")[0]
    return f"lifenote CLI on {host}"


def device_login(*, scopes: list[str] | None = None,
                 name: str | None = None,
                 open_browser: bool = True) -> dict:
    """
    Run the device-authorization flow. Blocks until the user approves (or
    until the device code expires). Returns the token response dict on
    success; raises RuntimeError otherwise.
    """
    scopes = scopes or ["journal:read", "chat:read"]
    name = name or _agent_name()

    # 1. Request device code
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{base_url()}/api/agent/v1/device/code",
            json={"name": name, "scopes": scopes, "client_kind": "cli"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"device/code failed: {r.status_code} {r.text}")
        body = r.json()

    user_code = body["user_code"]
    verify = body.get("verification_uri_complete") or body["verification_uri"]
    interval = body.get("interval", 5)
    expires_in = body.get("expires_in", 600)
    device_code = body["device_code"]

    print()
    print(f"  Open this in your browser: {verify}")
    print(f"  Or visit {body['verification_uri']} and enter: {user_code}")
    print()

    if open_browser:
        try:
            webbrowser.open(verify)
        except Exception:
            pass

    # 2. Poll for token
    deadline = time.time() + expires_in
    with httpx.Client(timeout=30.0) as client:
        while time.time() < deadline:
            time.sleep(interval)
            r = client.post(
                f"{base_url()}/api/agent/v1/device/token",
                json={"device_code": device_code},
            )
            if r.status_code == 200:
                return r.json()
            try:
                err = r.json().get("error")
            except Exception:
                err = None
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 2
                continue
            if err in ("access_denied", "expired_token"):
                raise RuntimeError(f"login {err}")
            # Other errors (invalid_grant etc.) — bail
            raise RuntimeError(f"login failed: {r.status_code} {r.text}")
    raise RuntimeError("login timed out — please run `lifenote auth login` again")
