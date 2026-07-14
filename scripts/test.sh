#!/bin/bash
set -Eeuo pipefail

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[+] Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet pytest pytest-cov ops
fi

if [ $# -eq 0 ]; then
    set -- -v
fi

exec "$VENV_DIR/bin/pytest" "$@"
