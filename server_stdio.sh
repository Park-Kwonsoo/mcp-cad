#!/bin/bash

# Setup and activate the virtual environment
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
VENV_DIR="$SCRIPT_DIR/.venv-cadquery" # Corrected venv name
VENV_ACTIVATE="$VENV_DIR/bin/activate"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
REQUIREMENTS_STAMP="$VENV_DIR/.requirements.stamp"

# Check if venv exists, create if not
if [ ! -d "$VENV_DIR" ]; then
  echo "Virtual environment not found at $VENV_DIR. Creating..." >&2
  uv venv "$VENV_DIR" >&2
  if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment." >&2
    exit 1
  fi
  echo "Virtual environment created." >&2

  # Activate and install requirements after creation
  echo "Activating environment..." >&2
  source "$VENV_ACTIVATE"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment after creation." >&2
    exit 1
  fi

else
  # Activate existing environment
  echo "Activating existing environment..." >&2
  source "$VENV_ACTIVATE"
  if [ $? -ne 0 ]; then
    echo "Error: Failed to activate existing virtual environment at $VENV_ACTIVATE." >&2
    exit 1
  fi
fi

if [ -f "$REQUIREMENTS_FILE" ]; then
  REQUIREMENTS_FINGERPRINT=$(cksum "$REQUIREMENTS_FILE" 2>/dev/null)
  CURRENT_REQUIREMENTS_FINGERPRINT=""
  if [ -f "$REQUIREMENTS_STAMP" ]; then
    CURRENT_REQUIREMENTS_FINGERPRINT=$(cat "$REQUIREMENTS_STAMP")
  fi

  if [ "$REQUIREMENTS_FINGERPRINT" != "$CURRENT_REQUIREMENTS_FINGERPRINT" ]; then
    echo "Ensuring server dependencies from $REQUIREMENTS_FILE..." >&2
    uv pip install -r "$REQUIREMENTS_FILE" >&2
    if [ $? -ne 0 ]; then
      echo "Error: Failed to install server dependencies." >&2
      exit 1
    fi
    printf '%s\n' "$REQUIREMENTS_FINGERPRINT" > "$REQUIREMENTS_STAMP"
  else
    echo "Server dependencies already synced." >&2
  fi
else
  echo "Warning: requirements.txt not found. Skipping dependency installation." >&2
fi

# Run the server in stdio mode, passing through any additional arguments
echo "Starting server in stdio mode..." >&2
python3 "$SCRIPT_DIR/server.py" --mode stdio "$@" # Ensure python3 is used here too
