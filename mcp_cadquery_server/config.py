from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServerConfig:
    models_dir: str = os.path.expanduser("~/.mcp/mcp-cad/models")
    ai_workspace_dir: str = os.path.expanduser("~/.mcp/mcp-cad/workspace")
    anthropic_model: str = "claude-opus-4-7"

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            models_dir=os.path.expanduser(os.environ.get("MCP_CAD_MODELS_DIR", cls.models_dir)),
            ai_workspace_dir=os.path.expanduser(os.environ.get("MCP_CAD_AI_WORKSPACE_DIR", cls.ai_workspace_dir)),
            anthropic_model=os.environ.get("MCP_CAD_AI_MODEL", cls.anthropic_model),
        )
