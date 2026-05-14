"""
Token storage + device-flow login.

Storage precedence (read order):
  1. LIFENOTE_API_TOKEN env var (for CI / Docker / headless agents)
  2. OS keychain (macOS Keychain, Windows Cred Manager, Linux libsecret)

Env-var path is essential: keyring fails or is unavailable in many headless
environments (CI runners, Docker without secrets manager, sandboxed agents).
"""
import os
import platform
import socket
import time
import webbrowser

import httpx

from .config import (
    ENV_TOKEN_VAR, KEYRING_SERVICE, KEYRING_USERNAME, base_url,
)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def get_token() -> str | None:
    """Env var first, keyring second. Returns the access token or None."""
    env = os.environ.get(ENV_TOKEN_VAR)
    if env:
        return env.strip()
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None


def set_token(token: str) -> None:
    """Store in keyring. Env var (if set) still wins on read; that's correct."""
    import keyring
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)


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
