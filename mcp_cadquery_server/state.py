import logging
import sys
import os
from typing import Dict, Any

# --- Logging Setup (Application Level) ---
# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
    force=True # Force re-configuration if already configured elsewhere
)
log = logging.getLogger("mcp_cadquery_server") # Use a consistent logger name

# --- Global State ---
shape_results: Dict[str, Dict[str, Any]] = {}

# --- Global Path Configuration (Defaults & Placeholders) ---

# Define script directory early for use in finding runners or resources.
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default names/relative paths (can be overridden by CLI)
DEFAULT_OUTPUT_DIR_NAME = "shapes" # Main output directory within workspace
DEFAULT_RENDER_DIR_NAME = "renders" # Subdir within output dir for renders
