#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
VENV_DIR="$SCRIPT_DIR/.venv-cadquery"
PYTHON_BIN="$VENV_DIR/bin/python"
STAMP_FILE="$VENV_DIR/.editable-install.stamp"
PYPROJECT_FILE="$SCRIPT_DIR/pyproject.toml"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Creating server virtual environment at $VENV_DIR..." >&2
  uv venv "$VENV_DIR" >&2
fi

PYPROJECT_FINGERPRINT=$(cksum "$PYPROJECT_FILE" 2>/dev/null || true)
CURRENT_FINGERPRINT=""
if [ -f "$STAMP_FILE" ]; then
  CURRENT_FINGERPRINT=$(cat "$STAMP_FILE")
fi

if [ "$PYPROJECT_FINGERPRINT" != "$CURRENT_FINGERPRINT" ]; then
  if "$PYTHON_BIN" -c "import anthropic, cadquery, mcp, pydantic" >/dev/null 2>&1; then
    echo "Server dependencies already available." >&2
  else
    echo "Installing MCP CAD server package..." >&2
    uv pip install -e "$SCRIPT_DIR" --python "$PYTHON_BIN" >&2
  fi
  printf '%s\n' "$PYPROJECT_FINGERPRINT" > "$STAMP_FILE"
fi

echo "Starting MCP CAD server over stdio..." >&2
exec "$PYTHON_BIN" "$SCRIPT_DIR/server.py" "$@"
