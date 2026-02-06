#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Running all tests via Makefile"
make -C "$REPO_ROOT" test
