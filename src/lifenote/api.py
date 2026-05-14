"""Thin httpx wrapper for /api/agent/v1/* — handles auth header + JSON."""
import httpx

from .auth import get_token
from .config import base_url


class APIError(Exception):
    def __init__(self, status: int, body):
        self.status = status
        self.body = body
        super().__init__(f"{status}: {body}")


def _client(timeout: float = 30.0) -> httpx.Client:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers["User-Agent"] = "lifenote-cli/0.1.0"
    return httpx.Client(base_url=base_url(), headers=headers, timeout=timeout)


def get(path: str, params: dict | None = None) -> dict:
    with _client() as c:
        r = c.get(path, params=params or {})
    if r.status_code != 200:
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise APIError(r.status_code, body)
    return r.json()


def delete(path: str) -> dict:
    with _client() as c:
        r = c.delete(path)
    if r.status_code not in (200, 204):
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise APIError(r.status_code, body)
    return {} if r.status_code == 204 else r.json()
