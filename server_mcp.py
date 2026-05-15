#!/usr/bin/env python3
"""FastMCP wrapper — proper JSON-RPC 2.0 MCP server for CadQuery."""
import sys
import os
import uuid
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from mcp.server.fastmcp import FastMCP
from src.mcp_cadquery_server.handlers import (
    handle_execute_cadquery_script,
    handle_export_shape,
    handle_export_shape_to_svg,
    handle_get_shape_properties,
    handle_get_shape_description,
)
from src.mcp_cadquery_server.models import ExecuteCadqueryScriptArgs

mcp = FastMCP("mcp-cad")

DEFAULT_WORKSPACE = os.path.expanduser("~/.mcp/mcp-cad/workspace")
os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)


@mcp.tool()
def execute_cadquery_script(
    script: str,
    workspace_path: str = DEFAULT_WORKSPACE,
    parameters: Optional[Dict[str, Any]] = None,
) -> dict:
    """CadQuery 스크립트를 실행하고 result_id를 반환합니다. STL 내보내기에 이 result_id를 사용하세요."""
    args = ExecuteCadqueryScriptArgs(
        workspace_path=workspace_path,
        script=script,
        parameters=parameters,
    )
    request_id = str(uuid.uuid4())[:8]
    return handle_execute_cadquery_script(args, request_id)


@mcp.tool()
def export_shape(
    result_id: str,
    filename: str,
    workspace_path: str = DEFAULT_WORKSPACE,
    shape_index: int = 0,
    format: Optional[str] = None,
) -> dict:
    """실행된 CadQuery 결과를 STL/STEP 파일로 내보냅니다. format은 'STL' 또는 'STEP'."""
    request = {
        "workspace_path": workspace_path,
        "result_id": result_id,
        "shape_index": shape_index,
        "filename": filename,
        "format": format,
        "options": {},
    }
    return handle_export_shape(request)


@mcp.tool()
def export_shape_to_svg(
    result_id: str,
    workspace_path: str = DEFAULT_WORKSPACE,
    shape_index: int = 0,
    filename: Optional[str] = None,
) -> dict:
    """실행된 CadQuery 결과를 SVG 미리보기 이미지로 내보냅니다."""
    request = {
        "workspace_path": workspace_path,
        "result_id": result_id,
        "shape_index": shape_index,
        "filename": filename,
        "options": {},
    }
    return handle_export_shape_to_svg(request)


@mcp.tool()
def get_shape_properties(result_id: str, shape_index: int = 0) -> dict:
    """CadQuery 결과의 부피, 면적, 바운딩 박스 등 물리적 속성을 반환합니다."""
    return handle_get_shape_properties({"result_id": result_id, "shape_index": shape_index})


@mcp.tool()
def get_shape_description(result_id: str, shape_index: int = 0) -> dict:
    """CadQuery 결과 형상을 텍스트로 설명합니다."""
    return handle_get_shape_description({"result_id": result_id, "shape_index": shape_index})


if __name__ == "__main__":
    mcp.run(transport="stdio")
