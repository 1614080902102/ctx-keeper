"""Adapter for OpenAI Codex / codex-cli conversation storage and retrieval."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .types import ConversationSnapshot, Message

CODEX_DIR = Path.home() / ".codex"
CODEX_SESSIONS_DIR = CODEX_DIR / "sessions"
CODEX_ARCHIVED_DIR = CODEX_DIR / "archived_sessions"
CODEX_DB = CODEX_DIR / "state_5.sqlite"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ts_to_dt(ts: int | float | None) -> datetime:
    """Convert a Unix timestamp (seconds) to an aware UTC datetime."""
    if ts is None:
        return datetime.now(tz=timezone.utc)
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _extract_text(content: list | str | None) -> str:
    """Flatten a content field (str or list of content blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            text = block.get("text") or block.get("content") or ""
            if text:
                parts.append(str(text))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def count_messages(path: Path) -> int:
    """Count response_item lines whose role is 'user' or 'assistant'."""
    if not path.exists():
        return 0
    count = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "response_item":
                    continue
                role = event.get("payload", {}).get("role", "")
                if role in ("user", "assistant"):
                    count += 1
    except OSError:
        pass
    return count


def _snapshot_from_jsonl(path: Path) -> ConversationSnapshot | None:
    """Build a ConversationSnapshot from a raw jsonl file (fallback path)."""
    session_id: str = ""
    title: str = ""
    created_at: datetime = datetime.now(tz=timezone.utc)
    tokens: int = 0

    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                if etype == "session_meta":
                    payload = event.get("payload", {})
                    session_id = payload.get("id", "")
                    raw_ts = event.get("timestamp") or payload.get("timestamp")
                    if raw_ts:
                        try:
                            created_at = datetime.fromisoformat(
                                raw_ts.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass
                elif etype == "response_item" and not title:
                    role = event.get("payload", {}).get("role", "")
                    if role == "user":
                        text = _extract_text(
                            event.get("payload", {}).get("content")
                        )
                        title = text.strip()[:80] or "Untitled"
    except OSError:
        return None

    if not session_id:
        # Use filename stem as session_id when meta event is missing
        session_id = path.stem

    return ConversationSnapshot(
        agent="codex",
        session_id=session_id,
        title=title or path.stem,
        provider="unknown",
        project="unknown",
        created_at=created_at,
        updated_at=created_at,
        tokens=tokens,
        path=path,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect() -> bool:
    """Return True if Codex session storage exists on this machine."""
    return CODEX_SESSIONS_DIR.exists()


def list_sessions(
    include_archived: bool = False,
) -> list[ConversationSnapshot]:
    """Return all Codex sessions, preferring sqlite metadata when available."""
    if CODEX_DB.exists():
        try:
            return _list_from_sqlite(include_archived=include_archived)
        except sqlite3.Error:
            pass
    # Fallback: scan jsonl files directly
    return _list_from_jsonl(CODEX_SESSIONS_DIR, include_archived=include_archived)


def _list_from_sqlite(include_archived: bool = False) -> list[ConversationSnapshot]:
    db_uri = f"file:{CODEX_DB}?mode=ro"
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        # Try with archived column first, fall back to no WHERE if column doesn't exist
        where = "" if include_archived else "WHERE archived = 0"
        try:
            rows = conn.execute(
                f"""
                SELECT id, title, first_user_message, model_provider, cwd,
                       created_at, updated_at, rollout_path, tokens_used
                FROM threads
                {where}
                ORDER BY updated_at DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            # Column 'archived' doesn't exist, try without WHERE clause
            rows = conn.execute(
                """
                SELECT id, title, first_user_message, model_provider, cwd,
                       created_at, updated_at, rollout_path, tokens_used
                FROM threads
                ORDER BY updated_at DESC
                """
            ).fetchall()

    snapshots: list[ConversationSnapshot] = []
    for row in rows:
        raw_title: str = row["title"] or ""
        if not raw_title or raw_title.lower() == "untitled":
            raw_title = row["first_user_message"] or ""
        title = raw_title.strip()[:120] or "Untitled"

        rollout_path_str: str | None = row["rollout_path"]
        path = Path(rollout_path_str) if rollout_path_str else None
        if path and not path.exists():
            path = _find_session_path(row["id"])
        if path is None:
            continue  # skip if we can't locate the file

        # Extract project from cwd (last segment) if available
        cwd: str | None = row["cwd"]
        project = "unknown"
        if cwd:
            project = Path(cwd).name or "unknown"

        snapshots.append(
            ConversationSnapshot(
                agent="codex",
                session_id=row["id"],
                title=title,
                provider=row["model_provider"] or "unknown",
                project=project,
                created_at=_ts_to_dt(row["created_at"]),
                updated_at=_ts_to_dt(row["updated_at"]),
                tokens=int(row["tokens_used"] or 0),
                path=path,
            )
        )
    return snapshots


def _list_from_jsonl(
    base_dir: Path = CODEX_SESSIONS_DIR,
    include_archived: bool = False,
) -> list[ConversationSnapshot]:
    dirs = [base_dir]
    if include_archived and CODEX_ARCHIVED_DIR.exists():
        dirs.append(CODEX_ARCHIVED_DIR)

    snapshots: list[ConversationSnapshot] = []
    for d in dirs:
        for jsonl in sorted(d.rglob("*.jsonl"), reverse=True):
            snap = _snapshot_from_jsonl(jsonl)
            if snap is not None:
                snapshots.append(snap)
    return snapshots


def _find_session_path(session_id: str) -> Path | None:
    """Search sessions and archived_sessions for a jsonl matching session_id."""
    for search_dir in (CODEX_SESSIONS_DIR, CODEX_ARCHIVED_DIR):
        if not search_dir.exists():
            continue
        matches = list(search_dir.rglob(f"*{session_id}*.jsonl"))
        if matches:
            return matches[0]
    return None


def load_messages(path: Path) -> list[Message]:
    """Parse a Codex jsonl and return Message objects in order."""
    messages: list[Message] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event.get("type") != "response_item":
                    continue

                payload = event.get("payload", {})
                role = payload.get("role", "")
                if role not in ("user", "assistant"):
                    continue

                content = _extract_text(payload.get("content"))
                ts_str = event.get("timestamp")
                ts = None
                if ts_str:
                    ts = _parse_ts(ts_str)

                messages.append(Message(role=role, content=content, timestamp=ts))
    except OSError:
        pass
    return messages


def _parse_ts(ts_str: str | None) -> datetime | None:
    """Parse an ISO-format timestamp string to an aware UTC datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load_session(session_id: str) -> dict:
    """Load and return all parsed events from a session jsonl."""
    path = _find_session_path(session_id)
    if path is None:
        return {}
    events: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return {}
    return {"session_id": session_id, "path": str(path), "events": events}
