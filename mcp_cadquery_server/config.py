from __future__ import annotations

import os
import sys
from dataclasses import dataclass


def _default_data_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/mcp-cadquery")
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(app_data, "mcp-cadquery")
    return os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "mcp-cadquery")


_DEFAULT_DATA_DIR = _default_data_dir()


@dataclass(frozen=True)
class ServerConfig:
    models_dir: str = os.path.join(_DEFAULT_DATA_DIR, "models")
    ai_workspace_dir: str = os.path.join(_DEFAULT_DATA_DIR, "workspace")
    anthropic_model: str = "claude-opus-4-7"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            models_dir=os.path.expanduser(os.environ.get("MCP_CAD_MODELS_DIR", cls.models_dir)),
            ai_workspace_dir=os.path.expanduser(os.environ.get("MCP_CAD_AI_WORKSPACE_DIR", cls.ai_workspace_dir)),
            anthropic_model=os.environ.get("MCP_CAD_AI_MODEL", cls.anthropic_model),
        )
