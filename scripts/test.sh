#!/bin/bash
# Run every unit suite: shared library, machine charm, k8s charm.
#
# Each suite is invoked from its own directory so the matching
# pyproject.toml supplies the correct pythonpath. Extra arguments are
# forwarded to every pytest invocation, e.g:
#
#   ./scripts/test.sh -k incident
#
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[+] Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet pytest pytest-cov ops ruff
fi

PYTEST="$VENV_DIR/bin/pytest"

if [ $# -eq 0 ]; then
    set -- -q
fi

status=0

run_suite() {
    local name="$1"
    local dir="$2"
    local target="$3"
    shift 3
    echo
    echo "=== $name ==="
    if ! (cd "$dir" && "$PYTEST" "$target" "$@"); then
        status=1
    fi
}

# tests/unit, not tests/ — tests/integration drives a real Juju controller
# and must never run as part of the unit sweep.
run_suite "shared library" "$REPO_ROOT" "tests/unit/" "$@"
run_suite "machine charm" "$REPO_ROOT/charms/machine" "tests/" "$@"
run_suite "k8s charm" "$REPO_ROOT/charms/k8s" "tests/" "$@"

echo
if [ "$status" -eq 0 ]; then
    echo "All suites passed."
else
    echo "One or more suites FAILED."
fi
exit "$status"
