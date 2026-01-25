#!/usr/bin/env bash

# =============================================================================
# MIDI Studio - Minimal Bootstrap
# =============================================================================
# This script is intentionally minimal.
#
# Prerequisite:
#   - uv (system dependency): https://docs.astral.sh/uv/
#
# It delegates everything else to the Python CLI:
#   uv run ms setup
#
# Usage:
#   ./setup-minimal.sh [ms setup options]
# =============================================================================

set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKSPACE_ROOT"

if [[ ! -f ".ms-workspace" ]]; then
  echo "error: .ms-workspace not found (run from workspace root)" >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv not found in PATH" >&2
  echo "install: https://docs.astral.sh/uv/" >&2
  exit 2
fi

exec uv run ms setup "$@"
