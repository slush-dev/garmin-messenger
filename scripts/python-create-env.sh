#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"

echo "==> Creating venv at $VENV_DIR"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "==> Installing packages via Makefile"
make -C "$REPO_ROOT" build-python

echo "==> Done. Activate with: source .venv/bin/activate"
