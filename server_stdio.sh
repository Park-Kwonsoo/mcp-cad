#!/bin/bash

# Setup and activate the virtual environment
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
VENV_DIR="$SCRIPT_DIR/.venv-cadquery" # Corrected venv name
VENV_ACTIVATE="$VENV_DIR/bin/activate"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

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

  if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "Installing dependencies from $REQUIREMENTS_FILE..." >&2
    uv pip install -r "$REQUIREMENTS_FILE" >&2
    if [ $? -ne 0 ]; then
      echo "Error: Failed to install dependencies." >&2
      # Consider exiting or just warning depending on desired behavior
      # exit 1
    else
       echo "Dependencies installed." >&2
    fi
  else
    echo "Warning: requirements.txt not found. Skipping dependency installation." >&2
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

# Run the server in stdio mode, passing through any additional arguments
echo "Starting server in stdio mode..." >&2
python3 "$SCRIPT_DIR/server.py" --mode stdio "$@" # Ensure python3 is used here too
