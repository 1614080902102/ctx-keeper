"""Daily and weekly token usage summaries across Codex + Claude Code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DaySummary:
    date: str          # "2026-05-11"
    sessions: int
    tokens: int
    codex_tokens: int
    cc_tokens: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_all_snapshots():
    from ctx_keeper.adapters import claude as claude_adapter
    from ctx_keeper.adapters import codex as codex_adapter

    snapshots = []
    if claude_adapter.detect():
        snapshots.extend(claude_adapter.list_sessions())
    if codex_adapter.detect():
        snapshots.extend(codex_adapter.list_sessions())
    return snapshots


# ---------------------------------------------------------------------------
# Core stats functions
# ---------------------------------------------------------------------------


def daily_stats(days: int = 1) -> list[DaySummary]:
    """Return one DaySummary per day for the last *days* days, sorted descending."""
    snapshots = _load_all_snapshots()

    today = datetime.now(tz=timezone.utc).date()
    target_dates: list[date] = [today - timedelta(days=i) for i in range(days)]

    # Build a lookup: date_str -> {sessions, tokens, codex_tokens, cc_tokens}
    buckets: dict[str, dict] = {}
    for d in target_dates:
        buckets[d.isoformat()] = {"sessions": 0, "tokens": 0, "codex_tokens": 0, "cc_tokens": 0}

    for snap in snapshots:
        d = snap.updated_at.date().isoformat()
        if d not in buckets:
            continue
        b = buckets[d]
        b["sessions"] += 1
        b["tokens"] += snap.tokens
        if snap.agent == "codex":
            b["codex_tokens"] += snap.tokens
        else:
            b["cc_tokens"] += snap.tokens

    result = [
        DaySummary(
            date=d,
            sessions=b["sessions"],
            tokens=b["tokens"],
            codex_tokens=b["codex_tokens"],
            cc_tokens=b["cc_tokens"],
        )
        for d, b in buckets.items()
    ]

    # Sort descending (most recent first)
    result.sort(key=lambda s: s.date, reverse=True)
    return result


def weekly_stats() -> list[DaySummary]:
    """Return one DaySummary per day for the last 7 days."""
    return daily_stats(days=7)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def print_daily(summary: DaySummary) -> None:
    """Print a Rich-formatted single-day summary with all-time totals."""
    from rich.console import Console
    from rich.text import Text

    console = Console()

    today_label = "today"

    # Compute all-time totals
    snapshots = _load_all_snapshots()
    all_sessions = len(snapshots)
    all_tokens = sum(s.tokens for s in snapshots)

    console.print(f"\n[bold]ctx-keeper stats — {today_label}[/bold]\n")
    console.print(f"  Sessions ({today_label}): [cyan]{summary.sessions:,}[/cyan]")
    console.print(f"  Tokens   ({today_label}): [cyan]{summary.tokens:,}[/cyan]")
    console.print(f"    [dim]Codex :[/dim]  {summary.codex_tokens:,}")
    console.print(f"    [dim]Claude:[/dim]  {summary.cc_tokens:,}")
    console.print()
    console.print("  [bold]All time:[/bold]")
    console.print(f"    Total sessions : [cyan]{all_sessions:,}[/cyan]")
    console.print(f"    Total tokens   : [cyan]{all_tokens:,}[/cyan]")
    console.print()


def print_weekly(summaries: list[DaySummary]) -> None:
    """Print a Rich table with weekly stats."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="ctx-keeper stats — last 7 days", show_lines=False)

    table.add_column("Date", style="bold")
    table.add_column("Sessions", justify="right", style="cyan")
    table.add_column("Tokens", justify="right", style="cyan")
    table.add_column("Codex", justify="right")
    table.add_column("Claude", justify="right")

    for s in summaries:
        table.add_row(
            s.date,
            f"{s.sessions:,}",
            f"{s.tokens:,}",
            f"{s.codex_tokens:,}",
            f"{s.cc_tokens:,}",
        )

    console.print()
    console.print(table)
    console.print()
