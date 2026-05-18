import logging
import sys
import os

# --- Logging Setup (Application Level) ---
# Avoid forcefully reconfiguring host/client logging on import.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        stream=sys.stderr,
    )
log = logging.getLogger("mcp_cadquery_server") # Use a consistent logger name

# --- Global Path Configuration (Defaults & Placeholders) ---

# Define script directory early for use in finding runners or resources.
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default names/relative paths (can be overridden by CLI)
DEFAULT_OUTPUT_DIR_NAME = "shapes" # Main output directory within workspace
DEFAULT_RENDER_DIR_NAME = "renders" # Subdir within output dir for renders
