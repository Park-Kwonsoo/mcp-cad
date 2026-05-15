import os
import sys
import subprocess
import shutil
import logging
import hashlib
import re
from typing import Optional

# Constants for environment setup
VENV_DIR = ".venv"
CACHE_ENV_VAR = "MCP_CADQUERY_CACHE_DIR"
PYTHON_VERSION = "3.11"
BASE_WORKSPACE_PACKAGES = ["cadquery==2.5.2"]
BASE_CADQUERY_VERSION = "2.5.2"

# Cache for workspace requirements.txt modification times
workspace_reqs_mtime_cache: dict[str, float] = {}
workspace_env_signature_cache: dict[str, tuple[str, Optional[float]]] = {}


def _default_cache_root() -> str:
    configured = os.environ.get(CACHE_ENV_VAR)
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches/mcp-cadquery")
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(local_app_data, "mcp-cadquery", "Cache")
    return os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "mcp-cadquery")


def _workspace_cache_key(workspace_path: str) -> str:
    resolved = os.path.realpath(os.path.abspath(workspace_path))
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    base_name = os.path.basename(resolved) or "workspace"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", base_name).strip("._") or "workspace"
    return f"{safe_name}-{digest}"


def get_workspace_cache_dir(workspace_path: str) -> str:
    return os.path.join(_default_cache_root(), "workspaces", _workspace_cache_key(workspace_path))


def get_workspace_venv_dir(workspace_path: str) -> str:
    return os.path.join(get_workspace_cache_dir(workspace_path), VENV_DIR)


def get_workspace_results_dir(workspace_path: str) -> str:
    return os.path.join(get_workspace_cache_dir(workspace_path), ".cq_results")


def _get_requirements_mtime(requirements_file: str) -> Optional[float]:
    if not os.path.isfile(requirements_file):
        return None
    return os.path.getmtime(requirements_file)

def _run_command_helper(command: list[str], check: bool = True, log_prefix: str = "Setup", **kwargs) -> subprocess.CompletedProcess:
    """
    Helper to run a command, capture output, and raise exceptions on failure.
    Uses logging.
    """
    # Ensure basic logging is configured if needed
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)

    log_msg_prefix = f"[{log_prefix}]"
    logging.info(f"{log_msg_prefix} Running command: {' '.join(command)}")
    try:
        process = subprocess.run(
            command,
            check=check,
            capture_output=True,
            text=True,
            **kwargs
        )
        logging.debug(f"{log_msg_prefix} Command stdout:\n{process.stdout}")
        if process.stderr:
            logging.debug(f"{log_msg_prefix} Command stderr:\n{process.stderr}")
        return process
    except FileNotFoundError as e:
        logging.error(f"{log_msg_prefix} Error: Command '{command[0]}' not found. Is it installed and in PATH?")
        raise e
    except subprocess.CalledProcessError as e:
        logging.error(f"{log_msg_prefix} Error running command: {' '.join(command)}")
        logging.error(f"{log_msg_prefix} Exit code: {e.returncode}")
        if e.stdout:
            logging.error(f"{log_msg_prefix} Stdout:\n{e.stdout}")
        if e.stderr:
            logging.error(f"{log_msg_prefix} Stderr:\n{e.stderr}")
        raise e
    except Exception as e:
        logging.error(f"{log_msg_prefix} An unexpected error occurred running command: {e}")
        raise e


def _base_cadquery_available(python_exe: str, log_prefix: str) -> bool:
    command = [
        python_exe,
        "-c",
        "import cadquery; print(cadquery.__version__)",
    ]
    try:
        process = _run_command_helper(command, check=False, log_prefix=log_prefix)
    except Exception as exc:
        logging.info(f"[{log_prefix}] Base CadQuery import check failed: {exc}")
        return False
    installed_version = process.stdout.strip()
    if process.returncode == 0 and installed_version == BASE_CADQUERY_VERSION:
        logging.info(f"[{log_prefix}] Base CadQuery {installed_version} already installed.")
        return True
    logging.info(
        f"[{log_prefix}] Base CadQuery install needed. "
        f"Return code: {process.returncode}, detected version: {installed_version or 'none'}"
    )
    return False


def _ensure_uv_available(log_prefix: str) -> None:
    if not shutil.which("uv"):
        msg = "Error: Python 'uv' is not installed or not in PATH. Please install it: https://github.com/astral-sh/uv"
        logging.error(f"[{log_prefix}] {msg}")
        raise FileNotFoundError(msg)


def prepare_workspace_env(workspace_path: str) -> str:
    """
    Ensures a virtual environment exists in the workspace, creates it if not,
    and installs dependencies from workspace/requirements.txt using uv.

    Args:
        workspace_path: The absolute path to the workspace directory.

    Returns:
        The absolute path to the Python executable within the workspace venv.

    Raises:
        FileNotFoundError: If 'uv' is not found or workspace_path is invalid.
        RuntimeError: If environment setup fails.
    """
    log_prefix = f"WorkspaceEnv({os.path.basename(workspace_path)})"
    logging.info(f"[{log_prefix}] Ensuring environment for workspace: {workspace_path}")

    if not os.path.isdir(workspace_path):
        msg = f"Workspace path does not exist or is not a directory: {workspace_path}"
        logging.error(f"[{log_prefix}] {msg}")
        raise FileNotFoundError(msg)

    # 1. Define paths and check the in-process fast path. Runtime artifacts
    # are kept out of user workspaces so STL output directories stay clean.
    venv_dir = get_workspace_venv_dir(workspace_path)
    requirements_file = os.path.join(workspace_path, "requirements.txt")
    bin_subdir = "Scripts" if sys.platform == "win32" else "bin"
    python_exe = os.path.join(venv_dir, bin_subdir, "python.exe" if sys.platform == "win32" else "python")
    try:
        current_requirements_mtime = _get_requirements_mtime(requirements_file)
    except OSError:
        current_requirements_mtime = None

    cached_signature = workspace_env_signature_cache.get(workspace_path)
    if (
        cached_signature == (python_exe, current_requirements_mtime)
        and os.path.exists(python_exe)
    ):
        logging.info(f"[{log_prefix}] Workspace environment unchanged. Reusing cached Python: {python_exe}")
        return python_exe

    uv_checked = False

    def ensure_uv_once() -> None:
        nonlocal uv_checked
        if uv_checked:
            return
        _ensure_uv_available(log_prefix)
        uv_checked = True

    try:
        # 3. Create venv if needed
        created_venv = False
        if not os.path.isdir(venv_dir) or not os.path.exists(python_exe):
            ensure_uv_once()
            os.makedirs(os.path.dirname(venv_dir), exist_ok=True)
            logging.info(f"[{log_prefix}] Creating virtual environment in {venv_dir} using Python {PYTHON_VERSION}...")
            _run_command_helper(["uv", "venv", venv_dir, "-p", PYTHON_VERSION], log_prefix=log_prefix)
            logging.info(f"[{log_prefix}] Virtual environment created.")
            created_venv = True
        else:
            logging.info(f"[{log_prefix}] Virtual environment already exists: {venv_dir}")

        if not os.path.exists(python_exe):
            msg = f"Python executable still not found at {python_exe} after check/creation."
            logging.error(f"[{log_prefix}] {msg}")
            raise RuntimeError(msg)

        # 4. Install base CadQuery packages once per server process for an already-seen env.
        if created_venv or cached_signature is None or cached_signature[0] != python_exe:
            if not created_venv and _base_cadquery_available(python_exe, log_prefix):
                logging.info(f"[{log_prefix}] Skipping base CadQuery install.")
            else:
                ensure_uv_once()
                logging.info(f"[{log_prefix}] Ensuring base CadQuery packages are installed in {venv_dir}...")
                _run_command_helper(["uv", "pip", "install", *BASE_WORKSPACE_PACKAGES, "--python", python_exe], log_prefix=log_prefix)
                logging.info(f"[{log_prefix}] Base CadQuery packages installed/verified.")
        else:
            logging.info(f"[{log_prefix}] Base CadQuery packages already verified for this server process.")

        # 5. Handle workspace requirements.txt
        install_reqs = False
        current_mtime: Optional[float] = None
        if os.path.isfile(requirements_file):
            try:
                current_mtime = os.path.getmtime(requirements_file)
                cached_mtime = workspace_reqs_mtime_cache.get(workspace_path)
                if current_mtime != cached_mtime:
                    install_reqs = True
                    logging.info(f"[{log_prefix}] requirements.txt changed (Current: {current_mtime}, Cached: {cached_mtime}). Will install.")
                else:
                    logging.info(f"[{log_prefix}] requirements.txt unchanged (mtime: {current_mtime}). Skipping install.")
            except OSError as mtime_err:
                logging.warning(f"[{log_prefix}] Could not get mtime for {requirements_file}: {mtime_err}. Assuming install needed.")
                install_reqs = True
        else:
            if workspace_path in workspace_reqs_mtime_cache:
                del workspace_reqs_mtime_cache[workspace_path]
            logging.info(f"[{log_prefix}] No requirements.txt found in workspace. Skipping additional dependencies.")

        if install_reqs:
            ensure_uv_once()
            logging.info(f"[{log_prefix}] Installing/syncing additional dependencies from {requirements_file} into {venv_dir}...")
            try:
                _run_command_helper(["uv", "pip", "install", "-r", requirements_file, "--python", python_exe], log_prefix=log_prefix)
                workspace_reqs_mtime_cache[workspace_path] = current_mtime
                logging.info(f"[{log_prefix}] Additional dependencies installed/synced. Updated mtime cache to {current_mtime}.")
            except Exception as install_err:
                if workspace_path in workspace_reqs_mtime_cache:
                    del workspace_reqs_mtime_cache[workspace_path]
                logging.error(f"[{log_prefix}] Failed to install dependencies from {requirements_file}. Error: {install_err}")
                raise RuntimeError(f"Failed to install dependencies from {requirements_file}") from install_err

        workspace_env_signature_cache[workspace_path] = (python_exe, current_mtime)
        logging.info(f"[{log_prefix}] Environment preparation complete.")
        return python_exe

    except FileNotFoundError:
        raise
    except (subprocess.CalledProcessError, Exception) as e:
        logging.error(f"[{log_prefix}] Failed to set up workspace environment: {e}")
        raise RuntimeError(f"Failed to set up workspace environment for {workspace_path}: {e}") from e
