from unittest.mock import MagicMock, patch

import pytest

from mcp_cadquery_server.ai_generator import (
    _extract_code_block,
    _validate_cadquery_code,
    generate_cadquery_code,
    modify_cadquery_code,
)


def _mock_response(code: str):
    response = MagicMock()
    response.content = [MagicMock(text=f"```python\n{code}\n```")]
    return response


def test_extract_code_block_with_fence():
    raw = (
        "Here is the code:\n"
        "```python\n"
        "import cadquery as cq\n"
        "result = cq.Workplane('XY').box(1, 1, 1)\n"
        "show_object(result)\n"
        "```\n"
        "Done."
    )

    code = _extract_code_block(raw)

    assert "import cadquery" in code
    assert "show_object" in code
    assert "```" not in code


def test_extract_code_block_without_fence():
    raw = "import cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)\nshow_object(result)"

    code = _extract_code_block(raw)

    assert "import cadquery" in code


def test_validate_rejects_external_imports():
    code = "import os\nimport cadquery as cq\nresult = cq.Workplane('XY').box(1, 1, 1)\nshow_object(result)"

    with pytest.raises(ValueError, match="Only cadquery imports"):
        _validate_cadquery_code(code)


def test_validate_rejects_cadquery_file_io_helpers():
    code = (
        "import cadquery as cq\n"
        "result = cq.Workplane('XY').box(1, 1, 1)\n"
        "cq.exporters.export(result, '/tmp/part.stl')\n"
        "show_object(result)"
    )

    with pytest.raises(ValueError, match="file import/export"):
        _validate_cadquery_code(code)


def test_generate_cadquery_code_calls_anthropic():
    generated = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 5)\nshow_object(result)"

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), patch(
        "mcp_cadquery_server.ai_generator.anthropic.Anthropic"
    ) as mock_client:
        instance = mock_client.return_value
        instance.messages.create.return_value = _mock_response(generated)

        code = generate_cadquery_code("10x10x5mm box")

    assert "import cadquery" in code
    assert "show_object" in code
    mock_client.assert_called_once_with(api_key="test-key")
    instance.messages.create.assert_called_once()
    assert instance.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"


def test_modify_cadquery_code_includes_existing_code():
    existing_code = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 5)\nshow_object(result)"
    generated = "import cadquery as cq\nresult = cq.Workplane('XY').box(20, 20, 5)\nshow_object(result)"

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), patch(
        "mcp_cadquery_server.ai_generator.anthropic.Anthropic"
    ) as mock_client:
        instance = mock_client.return_value
        instance.messages.create.return_value = _mock_response(generated)

        code = modify_cadquery_code(existing_code, "make the width and depth 20mm")

    assert "import cadquery" in code
    message_text = instance.messages.create.call_args.kwargs["messages"][0]["content"]
    assert existing_code in message_text


def test_generate_cadquery_code_with_image(tmp_path):
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    generated = "import cadquery as cq\nresult = cq.Workplane('XY').box(5, 5, 5)\nshow_object(result)"

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), patch(
        "mcp_cadquery_server.ai_generator.anthropic.Anthropic"
    ) as mock_client:
        instance = mock_client.return_value
        instance.messages.create.return_value = _mock_response(generated)

        code = generate_cadquery_code("image-based part", image_path=str(image_path))

    assert "import cadquery" in code
    messages_str = str(instance.messages.create.call_args)
    assert "image" in messages_str.lower()
    assert "base64" in messages_str.lower()


def test_generate_cadquery_code_rejects_non_image_file(tmp_path):
    text_path = tmp_path / "secret.txt"
    text_path.write_text("not an image")

    with pytest.raises(ValueError, match="Unsupported image file type"):
        generate_cadquery_code("use this", image_path=str(text_path))
