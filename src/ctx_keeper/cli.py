"""CLI entry point for ctx-keeper — the `ctx` command."""

from __future__ import annotations

import argparse
import sys

from ctx_keeper import __version__


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_dashboard() -> None:
    """Launch TUI dashboard."""
    from ctx_keeper.ui.dashboard import run
    run()


def _cmd_switch(args: argparse.Namespace) -> None:
    from ctx_keeper import switch

    if args.list:
        profiles = switch.list_profiles()
        current = switch.current_profile()
        print("Available profiles:")
        for p in profiles:
            marker = "→" if p == current else " "
            print(f"  {marker} {p}" + (" (current)" if p == current else ""))
        if not profiles:
            print("  (no profiles found in ~/.codex/profiles/)")
        return

    if args.current:
        print(switch.current_profile())
        return

    if not args.profile:
        print("Error: provide a profile name, --list, or --current", file=sys.stderr)
        sys.exit(1)

    try:
        result = switch.switch_profile(args.profile)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        profiles = switch.list_profiles()
        if profiles:
            print("Available profiles: " + ", ".join(profiles), file=sys.stderr)
        sys.exit(1)

    print(f"✓ Switched to: {result.profile} (was: {result.previous})")
    print(f"  Threads updated: {result.threads_updated}")
    print(f"  Available: {', '.join(result.profiles_available)}")


def _cmd_show(args: argparse.Namespace) -> None:
    """Show a single conversation using the Rich viewer."""
    from ctx_keeper.ui.viewer import show
    show(args.session_id)


def _cmd_search(args: argparse.Namespace) -> None:
    """Full-text search across all sessions using the search module."""
    from ctx_keeper.search import search

    results = search(args.query, limit=20)

    if not results:
        print(f"No sessions matched: {args.query!r}")
        return

    print(f"Found {len(results)} match(es) for {args.query!r}:\n")
    for r in results:
        snap = r.snapshot
        ts = snap.updated_at.strftime("%Y-%m-%d")
        count_str = f"x{r.match_count}" if r.match_count > 1 else ""
        mtype = f"{r.match_type}{count_str}"
        ctx_display = r.context.replace("\n", " ")[:60]
        print(
            f"  [{snap.agent:6}] {snap.session_id[:16]}  {ts}"
            f"  [{mtype:12}]  {ctx_display}"
        )


def _cmd_stats(args: argparse.Namespace) -> None:
    """Print token / session counts using the stats module."""
    from ctx_keeper.stats import daily_stats, weekly_stats, print_daily, print_weekly

    if args.week:
        summaries = weekly_stats()
        print_weekly(summaries)
    else:
        summaries = daily_stats(days=1)
        print_daily(summaries[0])


def _cmd_setup() -> None:
    from ctx_keeper import statusline

    result = statusline.setup_statusline()
    if result.cc_configured:
        print(f"✓ Claude Code statusLine configured: {result.cc_settings_path}")
    else:
        print(f"✗ Claude Code statusLine — could not write {result.cc_settings_path}", file=sys.stderr)

    if result.codex_configured:
        print(f"✓ Codex status_line configured: {result.codex_config_path}")
    else:
        print(f"✗ Codex status_line — could not write {result.codex_config_path}", file=sys.stderr)


def _cmd_unsetup() -> None:
    from ctx_keeper import statusline

    statusline.unsetup_statusline()
    print("✓ Removed ctx-keeper statusLine configuration")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ctx",
        description="AI agent context manager — track Codex + Claude Code conversations",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ctx-keeper {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    # switch
    sw = subparsers.add_parser("switch", help="Switch Codex profile")
    sw.add_argument("profile", nargs="?", help="Profile name to switch to")
    sw.add_argument("--list", action="store_true", help="List available profiles")
    sw.add_argument("--current", action="store_true", help="Show current profile name")

    # show
    show_p = subparsers.add_parser("show", help="Show a conversation")
    show_p.add_argument("session_id", help="Session ID to display")

    # search
    srch = subparsers.add_parser("search", help="Search conversations")
    srch.add_argument("query", help="Search query")

    # stats
    stats_p = subparsers.add_parser("stats", help="Token and session usage stats")
    stats_p.add_argument("--week", action="store_true", help="Show stats for the last 7 days")

    # setup / unsetup
    subparsers.add_parser("setup", help="Configure statusLine in Claude Code and Codex config")
    subparsers.add_parser("unsetup", help="Remove statusLine config from Claude Code and Codex")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point registered as the `ctx` console script."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        _cmd_dashboard()
        return

    if args.command == "switch":
        _cmd_switch(args)
    elif args.command == "show":
        _cmd_show(args)
    elif args.command == "search":
        _cmd_search(args)
    elif args.command == "stats":
        _cmd_stats(args)
    elif args.command == "setup":
        _cmd_setup()
    elif args.command == "unsetup":
        _cmd_unsetup()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
