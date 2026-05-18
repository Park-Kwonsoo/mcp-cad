import ast
import base64
import os
import re
import subprocess
from typing import Any

import anthropic


MODEL = os.environ.get("MCP_CAD_AI_MODEL", "claude-opus-4-7[1m]")
_OP_SECRET_REF = "op://Personal/Anthropic API/credential"
_DISALLOWED_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
_DISALLOWED_CADQUERY_ATTRS = {"exporters", "importers"}
_IMAGE_MEDIA_TYPES = {
    "gif": "image/gif",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
_MAX_IMAGE_BYTES = 20 * 1024 * 1024

_SYSTEM_PROMPT = """You are an expert CadQuery developer specializing in functional mechanical parts for 3D printing.

Generate precise, executable CadQuery Python code based on the user's description.

Rules:
- Always start with: import cadquery as cq
- The final shape MUST be registered with: show_object(result, name="part")
- Use only standard CadQuery 2.x API.
- No file I/O. No external imports beyond cadquery.
- Use millimeters as the unit.
- Add fillets/chamfers only when explicitly requested or structurally necessary.
- Return ONLY the Python code block, no explanation.

Example for "10x20x5mm rectangular box with 2mm hole in center":
```python
import cadquery as cq

result = (
    cq.Workplane("XY")
    .box(10, 20, 5)
    .faces(">Z")
    .workplane()
    .hole(2)
)
show_object(result, name="part")
```"""


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    try:
        result = subprocess.run(
            ["op", "read", _OP_SECRET_REF],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set and the key could not be read through 1Password CLI. "
            "Run the MCP server through `op run --env-file .env.1password -- ...`."
        ) from exc

    key = result.stdout.strip()
    if not key:
        raise RuntimeError("1Password returned an empty ANTHROPIC_API_KEY value.")
    return key


def _extract_code_block(raw: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _validate_cadquery_code(code: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Generated CadQuery code is not valid Python: {exc}") from exc

    imports_cadquery = False
    calls_show_object = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name != "cadquery":
                    raise ValueError("Only cadquery imports are allowed in generated code.")
                imports_cadquery = True
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or node.module != "cadquery":
                raise ValueError("Only cadquery imports are allowed in generated code.")
            imports_cadquery = True
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id == "show_object":
                    calls_show_object = True
                if node.func.id in _DISALLOWED_CALLS:
                    raise ValueError(f"Generated code may not call {node.func.id}().")
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "show_object":
                calls_show_object = True
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise ValueError("Generated code may not access dunder attributes.")
            if node.attr in _DISALLOWED_CADQUERY_ATTRS:
                raise ValueError("Generated code may not use CadQuery file import/export helpers.")

    if not imports_cadquery:
        raise ValueError("Generated code must import cadquery.")
    if not calls_show_object:
        raise ValueError("Generated code must call show_object(result, name=\"part\").")
    return code


def _response_text(response: Any) -> str:
    chunks = []
    for item in getattr(response, "content", []):
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
    if not chunks:
        raise ValueError("Anthropic response did not contain text content.")
    return "\n".join(chunks)


def _image_content(image_path: str) -> dict:
    resolved_path = os.path.abspath(os.path.expanduser(image_path))
    ext = os.path.splitext(resolved_path)[1].lower().lstrip(".")
    if ext not in _IMAGE_MEDIA_TYPES:
        raise ValueError(f"Unsupported image file type for {image_path!r}.")
    if not os.path.isfile(resolved_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if os.path.getsize(resolved_path) > _MAX_IMAGE_BYTES:
        raise ValueError("Image file is too large; maximum size is 20 MiB.")

    with open(resolved_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _IMAGE_MEDIA_TYPES[ext],
            "data": image_data,
        },
    }


def _call_anthropic(content: str | list[dict]) -> str:
    client = anthropic.Anthropic(api_key=_get_api_key())
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    code = _extract_code_block(_response_text(response))
    return _validate_cadquery_code(code)


def generate_cadquery_code(description: str, image_path: str | None = None) -> str:
    if image_path:
        content: str | list[dict] = [
            _image_content(image_path),
            {
                "type": "text",
                "text": f"Use this image as visual reference and generate CadQuery code for: {description}",
            },
        ]
    else:
        content = description

    return _call_anthropic(content)


def modify_cadquery_code(existing_code: str, instruction: str) -> str:
    prompt = f"""Here is the current CadQuery code:

```python
{existing_code}
```

Modification request: {instruction}

Update the code to satisfy the request. Preserve the existing structure where practical and return only executable CadQuery Python code."""

    return _call_anthropic(prompt)
