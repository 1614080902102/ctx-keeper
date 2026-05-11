"""Terminal status-line renderer — shows active Codex profile and token budget."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .switch import current_profile

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CODEX_DB = Path.home() / ".codex" / "state_5.sqlite"

# The command CC / Codex will execute to render the status string
_CC_CMD = "python3 -m ctx_keeper.statusline --cc"
_CODEX_CMD = "python3 -m ctx_keeper.statusline --codex"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SetupResult:
    cc_configured: bool
    codex_configured: bool
    cc_settings_path: Path
    codex_config_path: Path


# ---------------------------------------------------------------------------
# Quota helpers
# ---------------------------------------------------------------------------


def _read_5h_quota() -> str | None:
    """Return a formatted '5h: <pct>%' string, or None if unavailable."""
    if not CODEX_DB.exists():
        return None
    try:
        with closing(sqlite3.connect(str(CODEX_DB))) as conn:
            conn.row_factory = sqlite3.Row
            # Try common column names for rate-limit data
            for table in ("rate_limits", "quota", "limits"):
                try:
                    row = conn.execute(
                        f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 1"
                    ).fetchone()
                    if row is None:
                        continue
                    keys = row.keys()
                    # Look for a percentage-like column
                    for col in keys:
                        if "pct" in col.lower() or "percent" in col.lower() or "usage" in col.lower():
                            val = row[col]
                            if val is not None:
                                return f"5h: {int(val)}%"
                    # Look for used/limit pair
                    used_col = next((k for k in keys if "used" in k.lower()), None)
                    limit_col = next((k for k in keys if "limit" in k.lower() or "max" in k.lower()), None)
                    if used_col and limit_col:
                        used = row[used_col]
                        limit = row[limit_col]
                        if limit and limit > 0:
                            pct = int(100 * used / limit)
                            return f"5h: {pct}%"
                except sqlite3.OperationalError:
                    continue
    except sqlite3.Error:
        pass
    return None


# ---------------------------------------------------------------------------
# Render functions (called when the statusline script runs)
# ---------------------------------------------------------------------------


def render_cc_status() -> str:
    """Formatted status string for Claude Code's statusLine."""
    profile = current_profile()
    cwd = os.environ.get("PWD", os.getcwd())
    project = Path(cwd).name

    quota = _read_5h_quota()
    if quota:
        return f"[{profile}] {quota} | CC: {project}"
    return f"[{profile}] CC: {project}"


def render_codex_status() -> str:
    """Formatted status string for Codex's status_line."""
    profile = current_profile()
    quota = _read_5h_quota()
    if quota:
        return f"[{profile}] {quota}"
    return f"[{profile}]"


# ---------------------------------------------------------------------------
# Script generators (injected as shell commands into config files)
# ---------------------------------------------------------------------------


def generate_cc_statusline() -> dict:
    """Return the statusLine config object for Claude Code's settings.json."""
    return {"type": "command", "command": _CC_CMD}


def generate_codex_statusline() -> str:
    """Return the shell one-liner to put into Codex's status_line setting."""
    return _CODEX_CMD


# ---------------------------------------------------------------------------
# Setup / unsetup
# ---------------------------------------------------------------------------


def setup_statusline() -> SetupResult:
    """Install statusLine scripts into CC settings.json and Codex config.toml."""
    cc_configured = _install_cc_statusline()
    codex_configured = _install_codex_statusline()
    return SetupResult(
        cc_configured=cc_configured,
        codex_configured=codex_configured,
        cc_settings_path=CLAUDE_SETTINGS,
        codex_config_path=CODEX_CONFIG,
    )


def unsetup_statusline() -> None:
    """Remove statusLine/status_line keys installed by setup_statusline."""
    _remove_cc_statusline()
    _remove_codex_statusline()


# ---------------------------------------------------------------------------
# CC helpers
# ---------------------------------------------------------------------------


def _install_cc_statusline() -> bool:
    """Add/update statusLine in ~/.claude/settings.json. Returns True on success."""
    try:
        if CLAUDE_SETTINGS.exists():
            with CLAUDE_SETTINGS.open(encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            data = {}

        data["statusLine"] = generate_cc_statusline()

        CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write via temp file
        tmp = CLAUDE_SETTINGS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, CLAUDE_SETTINGS)
        return True
    except json.JSONDecodeError as e:
        print(f"Warning: ~/.claude/settings.json is malformed: {e}", file=sys.stderr)
        return False
    except OSError:
        return False


def _remove_cc_statusline() -> None:
    """Remove statusLine key from ~/.claude/settings.json."""
    if not CLAUDE_SETTINGS.exists():
        return
    try:
        with CLAUDE_SETTINGS.open(encoding="utf-8") as fh:
            data = json.load(fh)
        data.pop("statusLine", None)
        # Atomic write via temp file
        tmp = CLAUDE_SETTINGS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, CLAUDE_SETTINGS)
    except json.JSONDecodeError as e:
        print(f"Warning: ~/.claude/settings.json is malformed: {e}", file=sys.stderr)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Codex helpers — manual TOML editing to preserve comments/structure
# ---------------------------------------------------------------------------


def _install_codex_statusline() -> bool:
    """Add/update status_line under [tui] in ~/.codex/config.toml. Returns True on success."""
    try:
        if CODEX_CONFIG.exists():
            content = CODEX_CONFIG.read_text(encoding="utf-8")
        else:
            content = ""

        cmd = generate_codex_statusline()
        new_line = f'status_line = "{cmd}"\n'

        lines = content.splitlines(keepends=True)

        # Check if status_line already exists anywhere — update it in-place
        # Only match uncommented lines
        for i, line in enumerate(lines):
            if re.match(r"^\s*status_line\s*=", line) and not line.strip().startswith("#"):
                lines[i] = new_line
                # Atomic write via temp file
                tmp = CODEX_CONFIG.with_suffix(".toml.tmp")
                tmp.write_text("".join(lines), encoding="utf-8")
                os.replace(tmp, CODEX_CONFIG)
                return True

        # Find [tui] section and insert after it
        for i, line in enumerate(lines):
            if re.match(r"^\s*\[tui\]\s*$", line):
                lines.insert(i + 1, new_line)
                # Atomic write via temp file
                tmp = CODEX_CONFIG.with_suffix(".toml.tmp")
                tmp.write_text("".join(lines), encoding="utf-8")
                os.replace(tmp, CODEX_CONFIG)
                return True

        # No [tui] section — append one
        if content and not content.endswith("\n"):
            lines.append("\n")
        lines.append("\n[tui]\n")
        lines.append(new_line)
        # Atomic write via temp file
        tmp = CODEX_CONFIG.with_suffix(".toml.tmp")
        tmp.write_text("".join(lines), encoding="utf-8")
        os.replace(tmp, CODEX_CONFIG)
        return True
    except OSError:
        return False


def _remove_codex_statusline() -> None:
    """Remove status_line line from ~/.codex/config.toml."""
    if not CODEX_CONFIG.exists():
        return
    try:
        lines = CODEX_CONFIG.read_text(encoding="utf-8").splitlines(keepends=True)
        # Only remove uncommented status_line lines
        new_lines = [l for l in lines if not (re.match(r"^\s*status_line\s*=", l) and not l.strip().startswith("#"))]
        # Atomic write via temp file
        tmp = CODEX_CONFIG.with_suffix(".toml.tmp")
        tmp.write_text("".join(new_lines), encoding="utf-8")
        os.replace(tmp, CODEX_CONFIG)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# __main__ entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--cc" in sys.argv:
        print(render_cc_status())
    elif "--codex" in sys.argv:
        print(render_codex_status())
    else:
        print("Usage: python3 -m ctx_keeper.statusline [--cc | --codex]", file=sys.stderr)
        sys.exit(1)
