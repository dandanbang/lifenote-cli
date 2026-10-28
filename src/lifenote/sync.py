"""`lifenote sync <folder>`: one Markdown note per entry, Obsidian-ready.

- The first run pulls every entry (by id). Later runs ask only for entries
  written, edited, or given a new mentor reply since the last run, with a
  2-day overlap so a reply stamped in another timezone is never missed.
- The cursor lives in the folder (`.lifenote-sync.json`), so the job needs
  no other state, and two folders sync independently.
- Idempotent: a note is rewritten only when its bytes would change.
- Anything you write below the "your notes" line of a note is kept.
- Deleting an entry in Life Note does not delete its note here.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import base_url
from .render import obsidian_note

CURSOR_FILE = ".lifenote-sync.json"
OVERLAP = timedelta(days=2)
KEEP_MARKER = "%% Your notes below this line are kept by lifenote sync %%"


def note_path(entry) -> str:
    day = str(entry.get("date") or "")[:10] or "undated"
    return f"{day[:4]}/{day}-{int(entry['id'])}.md"


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
    """Pull changes into `folder`. Returns counts: new / updated / unchanged."""
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

    stats = {"new": 0, "updated": 0, "unchanged": 0}
    meta: dict = {}
    for entry in session.iter_entries(params, meta=meta):
        key = str(int(entry["id"]))
        rel = note_path(entry)
        path = folder / rel
        old_rel = files.get(key)
        if old_rel and old_rel != rel and (folder / old_rel).exists() and not path.exists():
            # The entry's date changed: move the note (and the user's tail) with it.
            path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(folder / old_rel, path)
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
    state = {
        "version": 1,
        "base_url": base_url(),
        "as_of": meta.get("as_of") or state.get("as_of"),
        "files": dict(sorted(files.items(), key=lambda kv: int(kv[0]))),
    }
    _write_atomic(folder / CURSOR_FILE, json.dumps(state, indent=2) + "\n")
    return stats
