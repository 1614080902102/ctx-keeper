"""Shared type definitions for agent adapters (conversation records, snapshots, etc.)."""

# TODO: implement
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


AgentName = Literal["codex", "claude"]


@dataclass
class ConversationSnapshot:
    """Represents a single saved conversation from an agent session."""
    agent: AgentName          # "codex" or "claude"
    session_id: str
    title: str
    provider: str             # codex profile name or "claude"
    project: str              # last segment of cwd, or "unknown"
    created_at: datetime
    updated_at: datetime
    tokens: int
    path: Path
    tags: list[str] = field(default_factory=list)


@dataclass
class Message:
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime | None = None
