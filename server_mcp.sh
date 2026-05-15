#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR/.venv-cadquery/bin/activate"
exec python3 "$SCRIPT_DIR/server_mcp.py"
