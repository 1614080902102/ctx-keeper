"""Conversation viewer — renders a single snapshot's messages in the terminal."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule

from ..adapters.types import ConversationSnapshot, Message

console = Console()

_TRUNCATE_AT = 1000
_PAGE_SIZE = 10


def _load_snapshot_and_messages(
    session_id: str,
) -> tuple[ConversationSnapshot | None, list[Message]]:
    """Search both adapters and return the snapshot + messages for session_id."""
    from ..adapters import claude as claude_adapter
    from ..adapters import codex as codex_adapter

    # Claude first
    if claude_adapter.detect():
        for snap in claude_adapter.list_sessions():
            if snap.session_id == session_id or session_id in snap.session_id:
                return snap, claude_adapter.load_messages(snap.path)

    # Codex fallback
    if codex_adapter.detect():
        for snap in codex_adapter.list_sessions():
            if snap.session_id == session_id or session_id in snap.session_id:
                return snap, codex_adapter.load_messages(snap.path)

    return None, []


def _render_message(index: int, msg: Message) -> None:
    """Print a single message with Rich formatting."""
    content = msg.content.strip()
    truncated = False
    if len(content) > _TRUNCATE_AT:
        content = content[:_TRUNCATE_AT]
        truncated = True

    ts_str = ""
    if msg.timestamp:
        ts_str = f"  {msg.timestamp.strftime('%Y-%m-%d %H:%M UTC')}"

    if msg.role == "user":
        label = Text(f"[{index}] USER{ts_str}", style="bold blue")
        body = Text(content, style="blue")
    elif msg.role == "assistant":
        label = Text(f"[{index}] ASSISTANT{ts_str}", style="bold green")
        body = Text(content, style="green")
    else:
        label = Text(f"[{index}] {msg.role.upper()}{ts_str}", style="bold yellow")
        body = Text(content, style="yellow")

    if truncated:
        body.append("\n[... truncated]", style="dim italic")

    console.print(label)
    console.print(body)
    console.print()


def show(session_id: str) -> None:
    """Display a single conversation in the terminal."""
    snapshot, messages = _load_snapshot_and_messages(session_id)

    if snapshot is None:
        console.print(
            f"[bold red]Error:[/bold red] session '{session_id}' not found",
            highlight=False,
        )
        sys.exit(1)

    # Header
    header = Text()
    header.append("Source:  ", style="dim")
    header.append(snapshot.agent, style="bold")
    header.append("\nProject: ", style="dim")
    header.append(snapshot.project)
    header.append("\nDate:    ", style="dim")
    header.append(snapshot.updated_at.strftime("%Y-%m-%d %H:%M UTC"))
    header.append("\nTitle:   ", style="dim")
    header.append(snapshot.title, style="bold")
    header.append("\nTokens:  ", style="dim")
    header.append(f"{snapshot.tokens:,}")
    header.append("\nID:      ", style="dim")
    header.append(snapshot.session_id, style="dim")

    console.print(Panel(header, title="Conversation", border_style="cyan"))
    console.print()

    if not messages:
        console.print("[dim]No messages found.[/dim]")
        return

    # Paginated display
    offset = 0
    while offset < len(messages):
        batch = messages[offset : offset + _PAGE_SIZE]
        for i, msg in enumerate(batch, start=offset + 1):
            _render_message(i, msg)

        offset += len(batch)
        remaining = len(messages) - offset

        if remaining > 0:
            console.print(
                Rule(f"{remaining} more message(s)", style="dim"),
            )
            try:
                answer = input("Show more? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if answer != "y":
                break
            console.print()


# Keep old name as alias for any callers using the stub API
def view_snapshot(snapshot: ConversationSnapshot) -> None:
    """Display the full message history for a given snapshot (legacy entry point)."""
    show(snapshot.session_id)
