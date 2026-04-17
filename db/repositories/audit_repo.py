"""Append-only audit log. Every data-mutating event gets a row.

Events stored here also get appended to CHANGELOG.md so users can see a
human-readable history without opening the DB.
"""
from __future__ import annotations

from pathlib import Path

from db.session import get_conn
from utils.config import PROJECT_ROOT
from utils.time import now_iso

CHANGELOG_PATH = PROJECT_ROOT / "CHANGELOG.md"
_RUNTIME_MARKER = "## Runtime events (auto-appended)"


def log(event_type: str, detail: str | None = None) -> None:
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (occurred_at, event_type, detail) VALUES (?, ?, ?)",
            (ts, event_type, detail),
        )
    _append_changelog(ts, event_type, detail)


def recent(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT occurred_at, event_type, detail FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def _append_changelog(ts: str, event_type: str, detail: str | None) -> None:
    """Append a bullet under the runtime-events section in CHANGELOG.md. Best-effort."""
    try:
        if not CHANGELOG_PATH.exists():
            return
        text = CHANGELOG_PATH.read_text(encoding="utf-8")
        if _RUNTIME_MARKER not in text:
            text = text.rstrip() + f"\n\n{_RUNTIME_MARKER}\n\n*Automatically logged by the running app. Local-only.*\n"
        line = f"- `{ts}` **{event_type}**" + (f" — {detail}" if detail else "")
        text = text.rstrip() + "\n" + line + "\n"
        CHANGELOG_PATH.write_text(text, encoding="utf-8")
    except OSError:
        pass
