"""Offline tests for paging, export rendering, and `lifenote sync` (LIFE-907).

Run: PYTHONPATH=src python -m unittest discover -s tests
"""
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from lifenote import api, render, sync


def entry(eid, text="hello", date="2026-10-01 09:00:00", replies=(), analysis=None,
          updated="2026-10-01T01:00:00Z"):
    return {
        "id": eid, "date": date, "time": date, "content": text, "content_text": text,
        "created_at": "2026-10-01T01:00:00Z", "updated_at": updated, "mood": None,
        "emoji": None, "prompt": None, "word_count": len(text.split()),
        "analysis": analysis,
        "responses": [{"id": i, "mentor": m, "content": c, "response_time": "2026-10-01T09:00:05Z"}
                      for i, (m, c) in enumerate(replies, 1)],
    }


class FakeSession:
    """Stands in for api.Session: records params, serves a fixed list."""

    def __init__(self, entries, as_of="2026-10-28T00:00:00Z", reply_cursor=50):
        self.entries = entries
        self.as_of = as_of
        self.reply_cursor = reply_cursor
        self.calls = []

    def iter_entries(self, params, page_size=100, meta=None):
        self.calls.append(dict(params))
        if meta is not None:
            meta.setdefault("as_of", self.as_of)
            meta.setdefault("reply_cursor", self.reply_cursor)
        yield from self.entries


class PagingTests(unittest.TestCase):

    def _session(self, handler):
        sleeps = []
        client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
        return api.Session(client=client, sleep=sleeps.append), sleeps

    def test_after_id_pages_continue_from_the_last_id(self):
        seen = []

        def handler(request):
            after = int(request.url.params["after_id"])
            seen.append(after)
            ids = [i for i in range(1, 6) if i > after][:2]
            return httpx.Response(200, json={
                "entries": [{"id": i} for i in ids], "has_more": bool(ids) and ids[-1] < 5,
                "as_of": f"as_of-{after}"})

        s, _ = self._session(handler)
        meta = {}
        got = [e["id"] for e in s.iter_entries({"after_id": 0}, page_size=2, meta=meta)]
        self.assertEqual(got, [1, 2, 3, 4, 5])
        self.assertEqual(seen, [0, 2, 4])
        self.assertEqual(meta["as_of"], "as_of-0")  # the FIRST page's instant

    def test_offset_pages_when_there_is_no_after_id(self):
        def handler(request):
            off = int(request.url.params["offset"])
            ids = list(range(off, min(off + 2, 3)))
            return httpx.Response(200, json={"entries": [{"id": i} for i in ids],
                                             "has_more": off + 2 < 3})

        s, _ = self._session(handler)
        self.assertEqual([e["id"] for e in s.iter_entries({}, page_size=2)], [0, 1, 2])

    def test_per_minute_429_waits_and_retries_but_daily_429_does_not(self):
        calls = []

        def minute(request):
            calls.append(1)
            if len(calls) < 3:
                return httpx.Response(429, json={"error": "rate_limited",
                                                 "reason": "per-token per-minute limit exceeded"})
            return httpx.Response(200, json={"ok": True})

        s, sleeps = self._session(minute)
        self.assertEqual(s.get("/x"), {"ok": True})
        self.assertEqual(len(sleeps), 2)

        def daily(request):
            return httpx.Response(429, json={"error": "rate_limited",
                                             "reason": "per-token daily limit exceeded"})

        s, sleeps = self._session(daily)
        with self.assertRaises(api.APIError) as ctx:
            s.get("/x")
        self.assertEqual(ctx.exception.status, 429)
        self.assertEqual(sleeps, [])


class RenderTests(unittest.TestCase):

    def test_frontmatter_is_valid_yaml_for_awkward_values(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        e = entry(7, replies=[('Seneca "the Younger"', "x"), ("Rumi: poet", "y")],
                  analysis={"feelings": ["calm", 'quote"d'], "topics": ["a: b"], "people": []})
        e["mood"] = "ok\nnew line"
        note = render.obsidian_note(e)
        fm = yaml.safe_load(note.split("---")[1])
        self.assertEqual(fm["id"], 7)
        self.assertEqual(fm["mentors"], ['Seneca "the Younger"', "Rumi: poet"])
        self.assertEqual(fm["feelings"], ["calm", 'quote"d'])
        self.assertEqual(fm["mood"], "ok\nnew line")

    def test_mentor_replies_become_callouts_with_every_line_quoted(self):
        note = render.obsidian_note(entry(1, replies=[("Seneca", "line one\n\nline two")]))
        self.assertIn("> [!note] Seneca · 2026-10-01 09:00\n> line one\n>\n> line two\n", note)

    def test_export_flags_include_or_leave_out_analysis_and_mentors(self):
        rows = [entry(1, replies=[("Seneca", "reply")], analysis={"reflection": "deep"})]
        bare = render.export_md(rows, include_analysis=False, include_mentors=False)
        self.assertNotIn("reply", bare)
        self.assertNotIn("deep", bare)
        full = render.export_md(rows)
        self.assertIn("### Mentor replies", full)
        self.assertIn("deep", full)
        data = json.loads(render.export_json(rows, include_analysis=False, include_mentors=True))
        self.assertNotIn("analysis", data["entries"][0])
        self.assertEqual(data["entries"][0]["responses"][0]["content"], "reply")
        self.assertIn("mentor_replies", render.export_csv(rows).splitlines()[0])


class SyncTests(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def _read(self, rel):
        return (self.dir / rel).read_text(encoding="utf-8")

    def test_first_run_pulls_everything_then_reruns_are_idempotent(self):
        s = FakeSession([entry(1), entry(2, date="2026-10-02 10:00:00")])
        self.assertEqual(sync.sync(self.dir, s), {"new": 2, "updated": 0, "unchanged": 0, "skipped": 0})
        self.assertEqual(s.calls[0], {"with_responses": 1, "after_id": 0})
        self.assertTrue((self.dir / "2026/2026-10-02-2.md").exists())
        before = self._read("2026/2026-10-01-1.md")
        self.assertEqual(sync.sync(self.dir, s, full=True), {"new": 0, "updated": 0, "unchanged": 2, "skipped": 0})
        self.assertEqual(self._read("2026/2026-10-01-1.md"), before)

    def test_next_run_asks_for_edits_since_the_cursor_and_replies_after_the_reply_cursor(self):
        sync.sync(self.dir, FakeSession([entry(1)], as_of="2026-10-28T00:00:00Z", reply_cursor=41))
        s = FakeSession([], reply_cursor=57)
        sync.sync(self.dir, s)
        self.assertEqual(s.calls[0], {"with_responses": 1, "updated_since": "2026-10-26T00:00:00Z",
                                      "reply_after_id": 41})
        state = json.loads(self._read(sync.CURSOR_FILE))
        self.assertEqual(state["files"], {"1": "2026/2026-10-01-1.md"})
        self.assertEqual(state["reply_cursor"], 57)

    def test_an_edit_and_a_new_reply_rewrite_the_note_and_keep_the_users_tail(self):
        sync.sync(self.dir, FakeSession([entry(1, "first draft")]))
        path = self.dir / "2026/2026-10-01-1.md"
        path.write_text(path.read_text(encoding="utf-8") + "my own note\n", encoding="utf-8")
        changed = entry(1, "second draft", replies=[("Rumi", "a late reply")])
        self.assertEqual(sync.sync(self.dir, FakeSession([changed])),
                         {"new": 0, "updated": 1, "unchanged": 0, "skipped": 0})
        text = path.read_text(encoding="utf-8")
        self.assertIn("second draft", text)
        self.assertIn("> [!note] Rumi", text)
        self.assertNotIn("first draft", text)
        self.assertTrue(text.endswith(sync.KEEP_MARKER + "\nmy own note\n"))
        self.assertEqual(sync.sync(self.dir, FakeSession([changed])),
                         {"new": 0, "updated": 0, "unchanged": 1, "skipped": 0})

    def test_an_entry_without_its_text_never_blanks_a_note_or_moves_the_cursor(self):
        sync.sync(self.dir, FakeSession([entry(1, "kept words")], as_of="2026-10-01T00:00:00Z"))
        broken = entry(1)
        broken["content"] = broken["content_text"] = None
        stats = sync.sync(self.dir, FakeSession([broken], as_of="2026-10-28T00:00:00Z"))
        self.assertEqual(stats["skipped"], 1)
        self.assertIn("kept words", self._read("2026/2026-10-01-1.md"))
        self.assertEqual(json.loads(self._read(sync.CURSOR_FILE))["as_of"], "2026-10-01T00:00:00Z")

    def test_never_writes_or_moves_files_outside_the_folder(self):
        outside = self.dir.parent / f"outside-{self.dir.name}"
        outside.mkdir()
        secret = outside / "id_rsa"
        secret.write_text("secret")
        vault = self.dir / "vault"
        sync.sync(vault, FakeSession([entry(1)]))
        state = json.loads((vault / sync.CURSOR_FILE).read_text())
        state["files"]["1"] = f"../../{outside.name}/id_rsa"   # a tampered cursor
        (vault / sync.CURSOR_FILE).write_text(json.dumps(state))
        hostile = [entry(1, date="2026-10-02 09:00:00"),
                   entry(2, date="../../../tmp/x"), entry(3, date="/etc/passwd")]
        sync.sync(vault, FakeSession(hostile))
        self.assertEqual(secret.read_text(), "secret")
        self.assertTrue((vault / "undated/2.md").exists())
        self.assertTrue((vault / "undated/3.md").exists())
        for p in vault.rglob("*"):
            self.assertTrue(p.resolve().is_relative_to(vault.resolve()), p)

    def test_an_entry_whose_date_changed_moves_its_note(self):
        sync.sync(self.dir, FakeSession([entry(1, date="2026-10-01 09:00:00")]))
        sync.sync(self.dir, FakeSession([entry(1, date="2026-09-30 09:00:00")]))
        self.assertFalse((self.dir / "2026/2026-10-01-1.md").exists())
        self.assertTrue((self.dir / "2026/2026-09-30-1.md").exists())


if __name__ == "__main__":
    unittest.main()
