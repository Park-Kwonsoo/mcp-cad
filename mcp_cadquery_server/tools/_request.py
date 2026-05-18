from __future__ import annotations

import uuid
from typing import Any


def tool_request(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(uuid.uuid4())[:8],
        "arguments": arguments,
    }
