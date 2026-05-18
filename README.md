# MCP CadQuery Server

Stdio MCP server for building, exporting, inspecting, and AI-generating CadQuery
models. The server exposes CadQuery execution tools plus higher-level AI tools
that generate or modify CadQuery code with the Anthropic API and export STL
artifacts.

## Current Structure

```text
.
├── server.py                         # Python entrypoint for stdio MCP
├── mcp-cadquery-server.sh            # Launcher used by MCP clients
├── pyproject.toml                    # Package metadata and dependencies
├── docs/
│   └── mcp-registration.md           # Claude Code, Claude Desktop, Codex setup
├── mcp_cadquery_server/
│   ├── cli.py                        # CLI wrapper around stdio mode
│   ├── stdio_server.py               # JSON-RPC MCP stdio protocol handling
│   ├── mcp_api.py                    # Tool schema and dispatch bridge
│   ├── handlers.py                   # MCP tool handlers
│   ├── models.py                     # Pydantic tool argument schemas
│   ├── ai_generator.py               # Anthropic CadQuery generation/modification
│   ├── model_store.py                # AI model version metadata store
│   ├── core.py                       # CAD/STL analysis and transformation logic
│   ├── runner_core.py                # CadQuery script execution core
│   ├── cadquery_worker.py            # Worker process for CadQuery execution
│   ├── worker_pool.py                # Worker lifecycle management
│   ├── state.py                      # Shared logging/runtime state
│   └── env_setup.py                  # Environment setup helpers
└── tests/
    ├── test_mcp_runtime.py
    ├── test_model_store.py
    ├── test_ai_generator.py
    └── test_ai_model_tools.py
```

Dependencies are declared in `pyproject.toml`; this project does not use a
`requirements.txt`.

## Runtime Paths

Runtime artifacts are intentionally ignored by git:

- `.venv-cadquery/` - launcher-managed virtual environment
- `workspace/` - CadQuery execution workspace
- `shapes/`, `renders/` - generated exports/previews
- `models/` - repo-local generated model artifacts, if created from this cwd
- `~/.mcp/mcp-cad/models/` - default AI model version store
- `~/.mcp/mcp-cad/workspace/` - default AI generation workspace

Each AI-generated model is stored under `~/.mcp/mcp-cad/models/{model_id}/` with
versioned CadQuery source files (`v1.py`, `v2.py`, ...), `meta.json`, and the
latest STL path recorded in metadata.

## MCP Tools

The server currently registers these tools:

- `execute_cadquery_script`
- `build_and_export_stl`
- `create_printable_stl`
- `generate_model`
- `modify_model`
- `list_models`
- `export_shape`
- `export_shape_to_svg`
- `analyze_cad_file`
- `transform_stl_mesh`
- `compare_stl_meshes`
- `inspect_stl_sections`
- `inspect_stl_plane_sections`
- `detect_mount_features`
- `render_stl_preview`
- `validate_stl_solid`
- `solidify_stl_mesh`
- `probe_stl_tunnel`
- `get_shape_properties`
- `get_shape_description`

The AI tools use `ANTHROPIC_API_KEY` and default to the Anthropic API model
`claude-opus-4-7`. Override it with `MCP_CAD_AI_MODEL` if needed.

## Secrets

The server expects `ANTHROPIC_API_KEY` for `generate_model` and `modify_model`.
The recommended local setup uses 1Password CLI:

```dotenv
ANTHROPIC_API_KEY=op://Personal/Anthropic API/credential
```

Save that in `.env.1password`, then run the server through `op run`. The file
contains only a 1Password reference, not the secret value.

This repo intentionally does not use a project-scoped `.mcp.json`. Register the
server explicitly in each client. See [docs/mcp-registration.md](docs/mcp-registration.md).

## Running

The launcher creates `.venv-cadquery/` when needed, installs the package if
dependencies are missing or `pyproject.toml` changed, then starts stdio mode:

```bash
/opt/homebrew/bin/op run \
  --env-file /Users/kwonsoo/.mcp/mcp-cad/.env.1password \
  -- \
  /Users/kwonsoo/.mcp/mcp-cad/mcp-cadquery-server.sh
```

Without 1Password, export `ANTHROPIC_API_KEY` yourself before starting the
launcher. Non-AI tools do not need the Anthropic key.

For local manual execution:

```bash
./mcp-cadquery-server.sh
```

The process speaks MCP over stdin/stdout.

## Client Registration

Use the commands in [docs/mcp-registration.md](docs/mcp-registration.md) to
remove older `mcp-cad` or `cadquery` registrations and re-add this launcher for:

- Claude Code
- Claude Desktop
- Codex

All clients should call the same command:

```bash
/opt/homebrew/bin/op run \
  --env-file /Users/kwonsoo/.mcp/mcp-cad/.env.1password \
  -- \
  /Users/kwonsoo/.mcp/mcp-cad/mcp-cadquery-server.sh
```

## Development

Create or refresh the dev environment:

```bash
uv venv .venv-cadquery
uv pip install -e ".[test]" --python .venv-cadquery/bin/python
```

Run tests:

```bash
.venv-cadquery/bin/python -m pytest tests -q
```

Quick import check:

```bash
.venv-cadquery/bin/python -c "import mcp_cadquery_server.handlers; print('import OK')"
```

## AI Model Workflow

Typical client flow:

```text
generate_model("10x10x5mm rectangular box")
  -> model_id, stl_path, cadquery_code, version

modify_model(model_id, "Change the height to 6mm")
  -> same model_id, new stl_path, updated cadquery_code, incremented version

list_models()
  -> stored model metadata ordered by updated_at
```

Generated CadQuery code is validated before execution. The validator requires a
CadQuery import and `show_object(...)`, and blocks external imports, file I/O,
dynamic execution, and CadQuery import/export helpers in generated code.
