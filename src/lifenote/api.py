"""Thin httpx wrapper for /api/agent/v1/* — handles auth header + JSON."""
import time
from collections.abc import Iterator

import httpx

from . import __version__
from .auth import get_token
from .config import base_url

USER_AGENT = f"lifenote-cli/{__version__}"

# The server allows 60 requests/minute per token. A first sync of a large
# journal pages past that, so a per-minute 429 waits and retries instead of
# failing the run. Daily limits are not retried.
RATE_LIMIT_WAIT_SECONDS = 20
RATE_LIMIT_RETRIES = 6


class APIError(Exception):
    def __init__(self, status: int, body):
        self.status = status
        self.body = body
        super().__init__(f"{status}: {body}")


def _client(timeout: float = 30.0) -> httpx.Client:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers["User-Agent"] = USER_AGENT
    return httpx.Client(base_url=base_url(), headers=headers, timeout=timeout)


def _raise_for(r: httpx.Response) -> None:
    try:
        body = r.json()
    except Exception:
        body = r.text
    raise APIError(r.status_code, body)


def _is_minute_limit(r: httpx.Response) -> bool:
    if r.status_code != 429:
        return False
    try:
        return "per-minute" in str(r.json().get("reason", ""))
    except Exception:
        return False


class Session:
    """One connection (and one token lookup) for a run of many requests."""

    def __init__(self, client: httpx.Client | None = None, sleep=time.sleep):
        self._c = client or _client()
        self._sleep = sleep

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._c.close()

    def get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            r = self._c.get(path, params=params or {})
            if attempt < RATE_LIMIT_RETRIES and _is_minute_limit(r):
                self._sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            break
        if r.status_code != 200:
            _raise_for(r)
        return r.json()

    def iter_entries(self, params: dict, page_size: int = 100,
                     meta: dict | None = None) -> Iterator[dict]:
        """Every entry matching `params`, page by page.

        With after_id the next page continues from the last id seen;
        otherwise it uses offset. Stops when the server says has_more=false.
        `meta` gets the first page's as_of and reply_cursor: where to resume.
        """
        params = {**params, "limit": page_size}
        offset = 0
        while True:
            page_params = dict(params)
            if "after_id" not in params:
                page_params["offset"] = offset
            body = self.get("/api/agent/v1/entries", params=page_params)
            if meta is not None:
                meta.setdefault("as_of", body.get("as_of"))
                meta.setdefault("reply_cursor", body.get("reply_cursor"))
            entries = body.get("entries") or []
            yield from entries
            if not body.get("has_more") or not entries:
                return
            if "after_id" in params:
                params["after_id"] = entries[-1]["id"]
            else:
                offset += len(entries)


def get(path: str, params: dict | None = None) -> dict:
    with Session() as s:
        return s.get(path, params=params)


def delete(path: str) -> dict:
    with _client() as c:
        r = c.delete(path)
    if r.status_code not in (200, 204):
        _raise_for(r)
    return {} if r.status_code == 204 else r.json()
