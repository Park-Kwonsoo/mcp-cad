from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import ServerConfig
from .services.worker_pool import CadQueryWorkerPool


@dataclass
class AppContext:
    config: ServerConfig
    shape_results: dict[str, dict[str, Any]]
    worker_pool: CadQueryWorkerPool
