"""Full-text search over saved conversation snapshots (Codex + Claude Code)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .adapters.types import ConversationSnapshot


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    snapshot: ConversationSnapshot
    match_type: Literal["title", "project", "content"]
    context: str        # excerpt showing where the match was found
    match_count: int    # number of times query appears in this session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _excerpt(text: str, query: str, window: int = 50) -> str:
    """Return a snippet centred on the first occurrence of query.

    Format: ``...{window chars before}{match}{window chars after}...``
    Leading/trailing ellipses are omitted when the match is at the very
    start or end of the text.
    """
    lower_text = text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return text[:window * 2] if text else ""

    start = max(0, idx - window)
    end = min(len(text), idx + len(query) + window)

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _count_occurrences(text: str, query: str) -> int:
    """Count case-insensitive occurrences of query in text."""
    if not query:
        return 0
    lower_text = text.lower()
    lower_query = query.lower()
    count = 0
    start = 0
    while True:
        idx = lower_text.find(lower_query, start)
        if idx == -1:
            break
        count += 1
        start = idx + 1
    return count


def _iter_message_texts(path: Path):
    """Yield plain-text content strings from user/assistant messages in a jsonl.

    Handles both Claude Code format (type in {user, assistant}, message.content)
    and Codex format (type == response_item, payload.content).
    """
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

                # Claude Code format
                if etype in ("user", "assistant"):
                    msg = event.get("message", {})
                    content = msg.get("content")
                    yield _flatten_content(content)

                # Codex format
                elif etype == "response_item":
                    payload = event.get("payload", {})
                    role = payload.get("role", "")
                    if role in ("user", "assistant"):
                        content = payload.get("content")
                        yield _flatten_content(content)
    except OSError:
        return


def _flatten_content(content) -> str:
    """Flatten content (str, list of blocks, or None) to plain text."""
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


# ---------------------------------------------------------------------------
# Content search
# ---------------------------------------------------------------------------


def _search_content(snapshot: ConversationSnapshot, query: str) -> SearchResult | None:
    """Scan snapshot.path for query in user/assistant messages.

    Returns a SearchResult if found, None otherwise.
    """
    lower_query = query.lower()
    total_count = 0
    first_excerpt: str | None = None

    for text in _iter_message_texts(snapshot.path):
        occurrences = _count_occurrences(text, lower_query)
        if occurrences:
            total_count += occurrences
            if first_excerpt is None:
                first_excerpt = _excerpt(text, query)

    if total_count == 0:
        return None

    return SearchResult(
        snapshot=snapshot,
        match_type="content",
        context=first_excerpt or "",
        match_count=total_count,
    )


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------


def search(
    query: str,
    limit: int = 20,
    *,
    metadata_only: bool = False,
) -> list[SearchResult]:
    """Full-text search across all Codex + Claude Code conversation sessions.

    Steps:
    1. Load all sessions from both adapters.
    2. Fast pass: check if query appears in title or project metadata.
    3. Content pass (unless metadata_only=True): open each jsonl and scan
       message text for the query.
    4. Return up to *limit* results sorted by updated_at descending.

    Parameters
    ----------
    query:
        Search string (case-insensitive).
    limit:
        Maximum number of results to return.
    metadata_only:
        When True skip the content scan (much faster, but misses body matches).
    """
    from .adapters import claude as claude_adapter
    from .adapters import codex as codex_adapter

    all_snapshots: list[ConversationSnapshot] = []
    if claude_adapter.detect():
        all_snapshots.extend(claude_adapter.list_sessions())
    if codex_adapter.detect():
        all_snapshots.extend(codex_adapter.list_sessions())

    lower_query = query.lower()
    results: list[SearchResult] = []
    seen_ids: set[str] = set()

    for snap in all_snapshots:
        if snap.session_id in seen_ids:
            continue

        # --- Fast pass: metadata ---
        if lower_query in snap.title.lower():
            seen_ids.add(snap.session_id)
            results.append(
                SearchResult(
                    snapshot=snap,
                    match_type="title",
                    context=snap.title,
                    match_count=_count_occurrences(snap.title, lower_query),
                )
            )
            continue

        if lower_query in snap.project.lower():
            seen_ids.add(snap.session_id)
            results.append(
                SearchResult(
                    snapshot=snap,
                    match_type="project",
                    context=snap.project,
                    match_count=_count_occurrences(snap.project, lower_query),
                )
            )
            continue

        # --- Content pass ---
        if not metadata_only:
            result = _search_content(snap, query)
            if result is not None:
                seen_ids.add(snap.session_id)
                results.append(result)

    # Sort by updated_at descending (most recent first)
    results.sort(key=lambda r: r.snapshot.updated_at, reverse=True)

    return results[:limit]
