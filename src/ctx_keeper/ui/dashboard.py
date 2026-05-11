"""Rich terminal dashboard — numbered-list interface for browsing context snapshots."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..adapters.types import ConversationSnapshot

console = Console()

_PAGE_SIZE = 20


def _load_all_sessions() -> list[ConversationSnapshot]:
    """Load sessions from both adapters, sorted newest first."""
    from ..adapters import claude as claude_adapter
    from ..adapters import codex as codex_adapter

    sessions: list[ConversationSnapshot] = []

    if claude_adapter.detect():
        sessions.extend(claude_adapter.list_sessions())

    if codex_adapter.detect():
        sessions.extend(codex_adapter.list_sessions())

    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    return sessions


def _build_table(
    sessions: list[ConversationSnapshot],
    page: int,
    total: int,
    source_filter: str,
    search_term: str,
) -> Table:
    """Render a Rich Table for the current page of sessions."""
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Source", width=8)
    table.add_column("Date", width=12)
    table.add_column("Project", width=20)
    table.add_column("Title")

    offset = page * _PAGE_SIZE
    for i, snap in enumerate(sessions[offset : offset + _PAGE_SIZE], start=offset + 1):
        source_style = "blue" if snap.agent == "claude" else "yellow"
        table.add_row(
            str(i),
            Text(f"[{snap.agent}]", style=source_style),
            snap.updated_at.strftime("%Y-%m-%d"),
            snap.project[:20],
            snap.title[:70],
        )

    # Build subtitle
    parts: list[str] = []
    if source_filter != "all":
        parts.append(f"source={source_filter}")
    if search_term:
        parts.append(f'search="{search_term}"')
    filter_note = f"  [{', '.join(parts)}]" if parts else ""

    pages_total = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    title = (
        f"ctx-keeper  —  {total} session(s){filter_note}"
        f"  (page {page + 1}/{pages_total})"
    )
    table.title = title
    return table


def _filter_sessions(
    sessions: list[ConversationSnapshot],
    source_filter: str,
    search_term: str,
) -> list[ConversationSnapshot]:
    result = sessions
    if source_filter != "all":
        result = [s for s in result if s.agent == source_filter]
    if search_term:
        term = search_term.lower()
        result = [s for s in result if term in s.title.lower() or term in s.project.lower()]
    return result


def _print_help() -> None:
    help_text = Text()
    help_text.append("Commands: ", style="bold")
    help_text.append("<number>", style="cyan")
    help_text.append(" view  ")
    help_text.append("n", style="cyan")
    help_text.append(" next page  ")
    help_text.append("p", style="cyan")
    help_text.append(" prev page  ")
    help_text.append("f", style="cyan")
    help_text.append(" filter source  ")
    help_text.append("s <term>", style="cyan")
    help_text.append(" search  ")
    help_text.append("q", style="cyan")
    help_text.append(" quit")
    console.print(Panel(help_text, border_style="dim"))


def run() -> None:
    """Launch the numbered-list dashboard."""
    all_sessions = _load_all_sessions()

    source_filter = "all"   # all | codex | claude
    search_term = ""
    page = 0

    _SOURCES = ["all", "codex", "claude"]

    while True:
        filtered = _filter_sessions(all_sessions, source_filter, search_term)
        total = len(filtered)
        pages_total = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        # Clamp page in case filters changed
        page = min(page, pages_total - 1)

        console.clear()
        table = _build_table(filtered, page, total, source_filter, search_term)
        console.print(table)
        _print_help()

        try:
            raw = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not raw:
            continue

        cmd = raw.lower()

        if cmd == "q":
            break

        if cmd == "n":
            if page < pages_total - 1:
                page += 1
            else:
                console.print("[dim]Already on last page.[/dim]")
            continue

        if cmd == "p":
            if page > 0:
                page -= 1
            else:
                console.print("[dim]Already on first page.[/dim]")
            continue

        if cmd == "f":
            idx = _SOURCES.index(source_filter)
            source_filter = _SOURCES[(idx + 1) % len(_SOURCES)]
            page = 0
            continue

        if cmd.startswith("s "):
            search_term = raw[2:].strip()
            page = 0
            continue

        # Numeric selection
        try:
            number = int(raw)
        except ValueError:
            # Treat as search term
            search_term = raw
            page = 0
            continue

        offset = page * _PAGE_SIZE
        idx_in_filtered = number - 1  # user-facing 1-based index
        if idx_in_filtered < 0 or idx_in_filtered >= total:
            console.print(f"[red]Invalid number: {number}[/red]")
            continue

        snap = filtered[idx_in_filtered]

        # View the conversation
        console.clear()
        from .viewer import show as viewer_show
        viewer_show(snap.session_id)

        try:
            input("\nPress Enter to return to list...")
        except (EOFError, KeyboardInterrupt):
            console.print()

    console.print("[dim]Goodbye.[/dim]")


# Keep legacy stub name as no-op alias
def render_dashboard(snapshots: list[ConversationSnapshot]) -> None:
    """Legacy stub — use run() instead."""
    run()
