#!/usr/bin/env bash
# ctx-keeper installer
# Usage: bash install.sh

set -euo pipefail

# ── 1. Check Python 3.11+ ─────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c 'import sys; print(sys.version_info >= (3, 11))')
        if [ "$ver" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: Python 3.11+ is required. Please install it and re-run this script."
    exit 1
fi

echo "Using $($PYTHON --version)"

# ── 2. Install ctx-keeper ─────────────────────────────────────────────────────
REPO_URL="https://github.com/1614080902102/ctx-keeper.git"

if [ -f "pyproject.toml" ] && grep -q 'name = "ctx-keeper"' pyproject.toml 2>/dev/null; then
    # Running from inside the cloned repo — use editable install
    echo "Detected local repo — installing in editable mode..."
    "$PYTHON" -m pip install -e . --quiet
else
    # Fresh install from a clone
    echo "Cloning ctx-keeper..."
    git clone "$REPO_URL" ctx-keeper
    cd ctx-keeper
    "$PYTHON" -m pip install -e . --quiet
fi

# ── 3. Post-install setup ─────────────────────────────────────────────────────
"$PYTHON" -m ctx_keeper.cli setup

# ── 4. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "ctx-keeper installed successfully!"
echo "Run 'ctx --help' to get started."
