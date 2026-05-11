"""Adapter for Claude Code conversation storage and retrieval."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .types import ConversationSnapshot, Message


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str | None) -> datetime | None:
    """Parse an ISO-format timestamp string to an aware UTC datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_content(content) -> str:
    """Flatten a content field (str or list of content blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(str(text))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _project_from_cwd(cwd: str | None, fallback_dir_name: str) -> str:
    """Extract the project name from a cwd path or fall back to the encoded dir name."""
    if cwd:
        name = Path(cwd).name
        if name:
            return name
    # Dir names are like "-Users-yanbabyer-yanie-project"; split on "-" and take last segment
    parts = fallback_dir_name.lstrip("-").split("-")
    return parts[-1] if parts else "unknown"


def _snapshot_from_jsonl(path: Path) -> ConversationSnapshot | None:
    """Build a ConversationSnapshot by parsing a Claude Code .jsonl file."""
    session_id: str = path.stem
    title: str = ""
    cwd_value: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tokens: int = 0
    has_real_messages: bool = False

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
                if etype not in ("user", "assistant"):
                    continue

                has_real_messages = True
                ts = _parse_ts(event.get("timestamp"))

                # Track cwd from any message (user messages tend to have it)
                if cwd_value is None:
                    cwd_value = event.get("cwd")

                # session_id from explicit field (prefer over filename)
                sid = event.get("sessionId")
                if sid:
                    session_id = sid

                # Track timestamps
                if ts is not None:
                    if created_at is None:
                        created_at = ts
                    updated_at = ts

                # Extract title from first user message
                if not title and etype == "user":
                    msg = event.get("message", {})
                    content = msg.get("content")
                    text = _extract_content(content).strip()
                    # Skip injected IDE/hook lines (usually start with <)
                    if text.startswith("<"):
                        text = ""
                    title = text[:100] or "Untitled"

                # Sum tokens from assistant messages
                if etype == "assistant":
                    usage = event.get("message", {}).get("usage", {})
                    if usage:
                        tokens += int(usage.get("input_tokens", 0) or 0)
                        tokens += int(usage.get("output_tokens", 0) or 0)

    except OSError:
        return None

    if not has_real_messages:
        return None

    now = datetime.now(tz=timezone.utc)
    return ConversationSnapshot(
        agent="claude",
        session_id=session_id,
        title=title or "Untitled",
        provider="claude",
        project=_project_from_cwd(cwd_value, path.parent.name),
        created_at=created_at or now,
        updated_at=updated_at or now,
        tokens=tokens,
        path=path,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect() -> bool:
    """Return True if ~/.claude/projects/ exists on this machine."""
    return CLAUDE_PROJECTS_DIR.exists()


def list_sessions(base_dir: Path = CLAUDE_PROJECTS_DIR) -> list[ConversationSnapshot]:
    """Return all Claude Code sessions found under base_dir, sorted newest first."""
    if not base_dir.exists():
        return []
    snapshots: list[ConversationSnapshot] = []
    for jsonl in base_dir.rglob("*.jsonl"):
        snap = _snapshot_from_jsonl(jsonl)
        if snap is not None:
            snapshots.append(snap)
    snapshots.sort(key=lambda s: s.updated_at, reverse=True)
    return snapshots


def load_messages(path: Path) -> list[Message]:
    """Parse a Claude Code jsonl and return Message objects in order."""
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

                etype = event.get("type", "")
                if etype not in ("user", "assistant"):
                    continue

                msg = event.get("message", {})
                role = msg.get("role", etype)
                content = _extract_content(msg.get("content"))
                ts = _parse_ts(event.get("timestamp"))

                # Skip messages with no displayable text (thinking/tool_use only)
                if not content.strip():
                    continue

                messages.append(Message(role=role, content=content, timestamp=ts))
    except OSError:
        pass
    return messages


def load_session(session_id: str, base_dir: Path = CLAUDE_PROJECTS_DIR) -> dict:
    """Load raw session data for the given session_id."""
    matches = list(base_dir.rglob(f"*{session_id}*.jsonl"))
    if not matches:
        return {}
    path = matches[0]
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
