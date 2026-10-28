"""`lifenote sync <folder>`: one Markdown note per entry, Obsidian-ready.

- The first run pulls every entry (by id). Later runs ask only for entries
  written or edited since the last run (2-day overlap, so a Daily Insight
  refreshed just after an edit is picked up), plus entries with a mentor
  reply newer than the last reply seen (reply ids, which never go back).
- The cursor lives in the folder (`.lifenote-sync.json`), so the job needs
  no other state, and two folders sync independently.
- Idempotent: a note is rewritten only when its bytes would change.
- Anything you write below the "your notes" line of a note is kept.
- Deleting an entry in Life Note does not delete its note here.
- Never writes outside the folder, and never replaces a note with an empty
  one: an entry that arrives without its text is skipped, and the cursor
  stays put so the next run retries it.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import base_url
from .render import obsidian_note

CURSOR_FILE = ".lifenote-sync.json"
OVERLAP = timedelta(days=2)
KEEP_MARKER = "%% Your notes below this line are kept by lifenote sync %%"


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def note_path(entry) -> str:
    day = str(entry.get("date") or "")[:10]
    if not _DAY.fullmatch(day):
        return f"undated/{int(entry['id'])}.md"
    return f"{day[:4]}/{day}-{int(entry['id'])}.md"


def _inside(folder: Path, rel) -> Path | None:
    """folder/rel if it stays inside folder (rel may come from a JSON file), else None."""
    if not isinstance(rel, str) or not rel:
        return None
    path = (folder / rel).resolve()
    return path if path.is_relative_to(folder.resolve()) else None


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".lifenote-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _load_state(folder: Path) -> dict:
    try:
        state = json.loads((folder / CURSOR_FILE).read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def _with_kept_tail(text: str, existing: str | None) -> str:
    """The rendered note, plus whatever the user wrote below the marker."""
    tail = ""
    if existing and KEEP_MARKER in existing:
        tail = existing.split(KEEP_MARKER, 1)[1]
    return text + "\n" + KEEP_MARKER + (tail if tail else "\n")


def sync(folder, session, full: bool = False) -> dict:
    """Pull changes into `folder`. Returns counts: new / updated / unchanged / skipped."""
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    state = _load_state(folder)
    files: dict = state.get("files") or {}

    if full or not state.get("as_of"):
        params = {"with_responses": 1, "after_id": 0}
    else:
        since = datetime.fromisoformat(state["as_of"].replace("Z", "+00:00")) - OVERLAP
        params = {"with_responses": 1,
                  "updated_since": since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        if state.get("reply_cursor") is not None:
            params["reply_after_id"] = int(state["reply_cursor"])

    stats = {"new": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    meta: dict = {}
    for entry in session.iter_entries(params, meta=meta):
        key = str(int(entry["id"]))
        if entry.get("content_text") is None and entry.get("content") is None:
            stats["skipped"] += 1
            continue
        rel = note_path(entry)
        path = _inside(folder, rel)
        if path is None:
            stats["skipped"] += 1
            continue
        old_path = _inside(folder, files.get(key))
        if old_path and old_path != path and old_path.exists() and not path.exists():
            # The entry's date changed: move the note (and the user's tail) with it.
            path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old_path, path)
        existing = path.read_text(encoding="utf-8") if path.exists() else None
        text = _with_kept_tail(obsidian_note(entry), existing)
        if existing == text:
            stats["unchanged"] += 1
        else:
            _write_atomic(path, text)
            stats["new" if existing is None else "updated"] += 1
        files[key] = rel

    # The cursor is the instant the run STARTED reading, so anything that
    # changed mid-run is picked up next time. Saved only after a full pass:
    # an interrupted run simply redoes its window.
    keep = bool(stats["skipped"])
    as_of = state.get("as_of") if keep else (meta.get("as_of") or state.get("as_of"))
    reply_cursor = state.get("reply_cursor") if keep else meta.get("reply_cursor", state.get("reply_cursor"))
    state = {
        "version": 1,
        "base_url": base_url(),
        "as_of": as_of,
        "reply_cursor": reply_cursor,
        "files": dict(sorted(files.items(), key=lambda kv: int(kv[0]))),
    }
    _write_atomic(folder / CURSOR_FILE, json.dumps(state, indent=2) + "\n")
    return stats
