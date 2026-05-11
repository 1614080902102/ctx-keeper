"""Profile switcher — switches Codex profiles and syncs state_5.sqlite."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

CODEX_DIR = Path.home() / ".codex"
CODEX_PROFILES_DIR = CODEX_DIR / "profiles"
CODEX_AUTH = CODEX_DIR / "auth.json"
CODEX_AUTH_BAK = CODEX_DIR / "auth.json.bak"
CODEX_CONFIG = CODEX_DIR / "config.toml"
CODEX_DB = CODEX_DIR / "state_5.sqlite"


@dataclass
class SwitchResult:
    profile: str
    previous: str
    threads_updated: int
    profiles_available: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_provider_from_config(config_path: Path) -> str:
    """Read config.toml and return the model_provider value."""
    try:
        with config_path.open(encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("model_provider"):
                    # Expect: model_provider = "VALUE"
                    parts = stripped.split("=", 1)
                    if len(parts) == 2:
                        value = parts[1].strip().strip('"').strip("'")
                        if value:
                            return value
    except OSError:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_profiles() -> list[str]:
    """Return sorted list of profile names found in ~/.codex/profiles/."""
    if not CODEX_PROFILES_DIR.exists():
        return []
    return sorted(
        p.name
        for p in CODEX_PROFILES_DIR.iterdir()
        if p.is_dir()
    )


def current_profile() -> str:
    """Return the name of the currently active Codex profile."""
    if not CODEX_AUTH.exists():
        return "unknown"

    try:
        with CODEX_AUTH.open(encoding="utf-8") as fh:
            auth = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return "unknown"

    auth_mode = auth.get("auth_mode", "")

    if auth_mode == "chatgpt":
        return "chatgpt"

    # For any other auth mode (including apikey), read model_provider from config.toml
    if CODEX_CONFIG.exists():
        provider = _get_provider_from_config(CODEX_CONFIG)
        if provider != "unknown":
            return provider

    return "unknown"


def switch_profile(profile: str) -> SwitchResult:
    """Switch to a named Codex profile and sync model_provider in sqlite."""
    profile_dir = CODEX_PROFILES_DIR / profile

    # Step 1: Validate
    if not profile_dir.exists() or not profile_dir.is_dir():
        raise ValueError(
            f"Profile '{profile}' not found at {profile_dir}"
        )

    profile_auth = profile_dir / "auth.json"
    profile_config = profile_dir / "config.toml"

    if not profile_auth.exists():
        raise ValueError(
            f"Profile '{profile}' is missing auth.json at {profile_auth}"
        )
    if not profile_config.exists():
        raise ValueError(
            f"Profile '{profile}' is missing config.toml at {profile_config}"
        )

    # Record previous profile before overwriting
    previous = current_profile()

    # Step 2: Copy profile files (with backup of existing auth.json)
    if CODEX_AUTH.exists():
        shutil.copy2(CODEX_AUTH, CODEX_AUTH_BAK)

    try:
        shutil.copy2(profile_auth, CODEX_AUTH)
        shutil.copy2(profile_config, CODEX_CONFIG)
    except OSError as e:
        # Restore auth.json from backup if we partially succeeded
        if CODEX_AUTH_BAK.exists():
            shutil.copy2(CODEX_AUTH_BAK, CODEX_AUTH)
        raise RuntimeError(f"Profile switch failed: {e}") from e

    # Step 3: Sync model_provider in sqlite
    threads_updated = 0
    if CODEX_DB.exists():
        try:
            provider_value = _get_provider_from_config(profile_config)
            with closing(sqlite3.connect(str(CODEX_DB))) as conn:
                cursor = conn.execute(
                    "UPDATE threads SET model_provider = ?", (provider_value,)
                )
                threads_updated = cursor.rowcount
                conn.commit()
        except sqlite3.Error as exc:
            print(
                f"[ctx-keeper] Warning: profile files switched to '{profile}' "
                f"but sqlite UPDATE failed: {exc}",
                file=sys.stderr,
            )
            threads_updated = 0

    # Step 4: Return result
    return SwitchResult(
        profile=profile,
        previous=previous,
        threads_updated=threads_updated,
        profiles_available=list_profiles(),
    )
