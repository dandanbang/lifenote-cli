"""Entry -> Markdown (Obsidian notes, `export --format md`) and CSV rows.

Input is one entry from `GET /api/agent/v1/entries?with_responses=1`.
Output is deterministic (no "generated at" stamps), so re-rendering an
unchanged entry produces byte-identical text: that is what makes
`lifenote sync` idempotent.
"""
import csv
import io
import json


def _yaml_str(value) -> str:
    # A JSON string is a valid YAML double-quoted scalar (same escapes).
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_list(values) -> str:
    return "[" + ", ".join(_yaml_str(v) for v in values) + "]"


def _day(entry) -> str:
    return str(entry.get("date") or "")[:10]


def _clock(entry) -> str:
    t = str(entry.get("time") or entry.get("date") or "")
    return t[11:16] if len(t) >= 16 else ""


def _text(entry) -> str:
    return (entry.get("content_text") or entry.get("content") or "").strip()


def _mentors(entry) -> list[str]:
    seen = []
    for r in entry.get("responses") or []:
        name = r.get("mentor")
        if name and name not in seen:
            seen.append(name)
    return seen


def frontmatter(entry) -> str:
    analysis = entry.get("analysis") or {}
    lines = ["---", f"id: {int(entry['id'])}", f"date: {_day(entry)}"]
    if _clock(entry):
        lines.append(f"time: {_yaml_str(_clock(entry))}")
    for key in ("created_at", "updated_at"):
        if entry.get(key):
            lines.append(f"{key.replace('_at', '')}: {entry[key]}")
    for key in ("mood", "emoji", "prompt"):
        if entry.get(key):
            lines.append(f"{key}: {_yaml_str(entry[key])}")
    if _mentors(entry):
        lines.append(f"mentors: {_yaml_list(_mentors(entry))}")
    for key in ("feelings", "topics", "people"):
        if analysis.get(key):
            lines.append(f"{key}: {_yaml_list(analysis[key])}")
    lines += ["tags: [\"lifenote\"]", "source: \"Life Note\"", "---"]
    return "\n".join(lines)


def _quoted(text: str) -> list[str]:
    return [f"> {line}" if line.strip() else ">" for line in str(text).strip().splitlines()]


def analysis_md(analysis: dict | None) -> list[str]:
    if not analysis:
        return []
    out = ["## Daily Insight", ""]
    if analysis.get("reflection"):
        out += [str(analysis["reflection"]).strip(), ""]
    if analysis.get("key_insight"):
        out += [f"**Key insight:** {str(analysis['key_insight']).strip()}", ""]
    if analysis.get("quote"):
        author = analysis.get("quote_author")
        out += ["> [!quote]" + (f" {author}" if author else "")]
        out += _quoted(analysis["quote"]) + [""]
    return out


def responses_md(responses: list | None) -> list[str]:
    if not responses:
        return []
    out = ["## Mentor replies", ""]
    for r in responses:
        when = str(r.get("response_time") or "")[:16].replace("T", " ")
        title = (r.get("mentor") or "Mentor") + (f" · {when}" if when else "")
        out += [f"> [!note] {title}"] + _quoted(r.get("content") or "") + [""]
    return out


def entry_body(entry, include_analysis=True, include_mentors=True) -> list[str]:
    out = [_text(entry), ""]
    if include_analysis:
        out += analysis_md(entry.get("analysis"))
    if include_mentors:
        out += responses_md(entry.get("responses"))
    return out


def obsidian_note(entry) -> str:
    """The whole file `lifenote sync` writes for one entry."""
    title = _day(entry) + (f" {_clock(entry)}" if _clock(entry) else "")
    lines = [frontmatter(entry), "", f"# {title}", ""] + entry_body(entry)
    return "\n".join(lines).rstrip() + "\n"


def export_md(entries, include_analysis=True, include_mentors=True) -> str:
    out = ["# Life Note journal", ""]
    for e in entries:
        title = _day(e) + (f" {_clock(e)}" if _clock(e) else "")
        out += [f"## {title}", ""]
        body = entry_body(e, include_analysis, include_mentors)
        # One heading level down inside a multi-entry file.
        out += [("#" + line) if line.startswith("## ") else line for line in body]
    return "\n".join(out).rstrip() + "\n"


CSV_FIELDS = ["id", "date", "time", "mood", "emoji", "prompt", "word_count", "content",
              "updated_at"]
CSV_ANALYSIS = ["reflection", "key_insight", "quote", "quote_author", "feelings", "people",
                "topics"]


def export_csv(entries, include_analysis=True, include_mentors=True) -> str:
    fields = list(CSV_FIELDS)
    if include_analysis:
        fields += CSV_ANALYSIS
    if include_mentors:
        fields += ["mentor_replies"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for e in entries:
        row = {k: e.get(k) for k in CSV_FIELDS}
        row["date"] = _day(e)
        row["time"] = _clock(e)
        row["content"] = _text(e)
        if include_analysis:
            a = e.get("analysis") or {}
            for k in CSV_ANALYSIS:
                v = a.get(k)
                row[k] = ", ".join(v) if isinstance(v, list) else v
        if include_mentors:
            row["mentor_replies"] = " || ".join(
                f"{r.get('mentor')}: {str(r.get('content') or '').strip()}"
                for r in e.get("responses") or [])
        w.writerow(row)
    return buf.getvalue()


def export_json(entries, include_analysis=True, include_mentors=True) -> str:
    out = []
    for e in entries:
        e = dict(e)
        if not include_analysis:
            e.pop("analysis", None)
        if not include_mentors:
            e.pop("responses", None)
        out.append(e)
    return json.dumps({"entries": out, "count": len(out)}, ensure_ascii=False, indent=2) + "\n"
