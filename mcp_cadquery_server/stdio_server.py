import asyncio
import sys
import json
from typing import Dict, Any, Optional

# Import necessary components from other modules
from .state import log
from .mcp_api import get_server_info, process_tool_request


MCP_PROTOCOL_VERSION = "2024-11-05"


def _jsonrpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _write_message(message: Dict[str, Any]) -> None:
    print(json.dumps(message, ensure_ascii=False), flush=True)


def _mcp_tools() -> list[Dict[str, Any]]:
    server_info = get_server_info()
    tools = []
    for tool in server_info.get("tools", []):
        tools.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}}),
        })
    return tools


def _call_tool(params: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    if not tool_name:
        raise ValueError("Missing tool name.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object.")

    request = {
        "request_id": params.get("_request_id", "stdio-request"),
        "tool_name": tool_name,
        "arguments": arguments,
    }
    response = process_tool_request(request)
    if not response:
        payload: Dict[str, Any] = {"success": True}
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}

    if response.get("type") == "tool_error":
        error_payload = {"error": response.get("error", "Unknown tool error")}
        return {
            "isError": True,
            "content": [{"type": "text", "text": json.dumps(error_payload, ensure_ascii=False)}],
        }

    payload = response.get("result", response)
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _handle_jsonrpc_request(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if not method:
        return _jsonrpc_error(request_id, -32600, "Invalid request: missing method.")

    # Notifications have no id and must not receive a response.
    if request_id is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        server_info = get_server_info()
        return _jsonrpc_result(request_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": server_info.get("server_name", "mcp-cadquery-server"),
                "version": server_info.get("version", "0.0.0"),
            },
        })
    if method == "ping":
        return _jsonrpc_result(request_id, {})
    if method == "tools/list":
        return _jsonrpc_result(request_id, {"tools": _mcp_tools()})
    if method == "tools/call":
        if not isinstance(params, dict):
            return _jsonrpc_error(request_id, -32602, "Invalid params: expected object.")
        params = dict(params)
        params["_request_id"] = str(request_id)
        try:
            return _jsonrpc_result(request_id, _call_tool(params))
        except Exception as exc:
            return _jsonrpc_result(request_id, {
                "isError": True,
                "content": [{"type": "text", "text": str(exc)}],
            })
    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        return _jsonrpc_result(request_id, {key: []})

    return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def _handle_legacy_tool_request(request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if "tool_name" not in request_data or "request_id" not in request_data:
        raise ValueError("Invalid MCP request format (missing tool_name or request_id)")
    return process_tool_request(request_data)

async def run_stdio_mode() -> None:
    """Runs the server in MCP stdio mode, reading JSON requests from stdin."""
    log.info("Starting server in Stdio mode. Reading from stdin...")

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    try:
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    except Exception as e:
         log.error(f"Error connecting read pipe for stdin: {e}. Stdio mode may not work.", exc_info=True)
         _write_message(_jsonrpc_error(None, -32000, f"Failed to connect stdin: {e}"))
         return # Cannot proceed without stdin

    request_data: Optional[Dict[str, Any]] = None # Define request_data outside loop for error handling scope
    while True:
        try:
            line_bytes = await reader.readline()
            if not line_bytes: break # EOF
            line = line_bytes.decode('utf-8').strip()
            if not line: continue
            log.debug(f"Received stdio line: {line}")
            request_data = json.loads(line) # Assign here
            if not isinstance(request_data, dict):
                raise ValueError("Invalid request format: expected JSON object.")

            if request_data.get("jsonrpc") == "2.0" or "method" in request_data:
                response = _handle_jsonrpc_request(request_data)
            else:
                response = _handle_legacy_tool_request(request_data)
            if response:
                _write_message(response)
        except json.JSONDecodeError as e:
            log.error(f"Failed to decode JSON from stdin: {e}")
            _write_message(_jsonrpc_error(None, -32700, f"Invalid JSON received: {e}"))
        except ValueError as e: # Catch validation errors
             log.error(f"Invalid request format: {e}")
             req_id = request_data.get("request_id", "unknown") if isinstance(request_data, dict) else "unknown"
             if isinstance(request_data, dict) and (request_data.get("jsonrpc") == "2.0" or "method" in request_data):
                 _write_message(_jsonrpc_error(request_data.get("id"), -32600, str(e)))
             else:
                 _write_message({"type": "tool_error", "request_id": req_id, "error": f"Invalid request format: {e}"})
        except Exception as e:
             log.error(f"Error processing stdio request: {e}", exc_info=True)
             req_id = request_data.get("request_id", "unknown") if isinstance(request_data, dict) else "unknown"
             if isinstance(request_data, dict) and (request_data.get("jsonrpc") == "2.0" or "method" in request_data):
                 _write_message(_jsonrpc_error(request_data.get("id"), -32603, f"Internal server error: {e}"))
             else:
                 _write_message({"type": "tool_error", "request_id": req_id, "error": f"Internal server error: {e}"})
        except KeyboardInterrupt: log.info("KeyboardInterrupt received, exiting stdio mode."); break
        except Exception as e: log.error(f"Unexpected error in stdio loop: {e}", exc_info=True); await asyncio.sleep(1)
