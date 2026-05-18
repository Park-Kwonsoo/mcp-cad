# MCP CAD Registration

This project does not use a project-scoped `.mcp.json`. Register the server in each client explicitly so the same command is used everywhere and secrets are injected through 1Password.

## Shared Command

Use the repository launcher through `op run`:

```bash
/opt/homebrew/bin/op run \
  --env-file /Users/kwonsoo/.mcp/mcp-cad/.env.1password \
  -- \
  /Users/kwonsoo/.mcp/mcp-cad/server_stdio.sh
```

The `.env.1password` file should contain only the 1Password reference:

```dotenv
ANTHROPIC_API_KEY=op://Personal/Anthropic API/credential
```

If `op` is installed somewhere else, replace `/opt/homebrew/bin/op` with the output of `which op`.

## Claude Code

Remove old registrations. Ignore "not found" errors.

```bash
claude mcp remove --scope local mcp-cad
claude mcp remove --scope project mcp-cad
claude mcp remove --scope user mcp-cad
claude mcp remove --scope local cadquery
claude mcp remove --scope project cadquery
claude mcp remove --scope user cadquery
```

Register the server at user scope:

```bash
claude mcp add \
  --scope user \
  --transport stdio \
  mcp-cad \
  -- \
  /opt/homebrew/bin/op run \
  --env-file /Users/kwonsoo/.mcp/mcp-cad/.env.1password \
  -- \
  /Users/kwonsoo/.mcp/mcp-cad/server_stdio.sh
```

Verify:

```bash
claude mcp get mcp-cad
claude mcp list
```

Inside Claude Code, `/mcp` should show `mcp-cad` connected.

## Claude Desktop

Open the Claude Desktop config:

```bash
open "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
```

In `mcpServers`, remove any existing `mcp-cad` or `cadquery` entry, then add:

```json
{
  "mcpServers": {
    "mcp-cad": {
      "command": "/opt/homebrew/bin/op",
      "args": [
        "run",
        "--env-file",
        "/Users/kwonsoo/.mcp/mcp-cad/.env.1password",
        "--",
        "/Users/kwonsoo/.mcp/mcp-cad/server_stdio.sh"
      ]
    }
  }
}
```

If the file already has other MCP servers, keep them and only replace the `mcp-cad` or `cadquery` entry. Restart Claude Desktop after editing.

## Codex

Remove old registrations. The previous local name may be `cadquery`.

```bash
codex mcp remove mcp-cad
codex mcp remove cadquery
```

Register the server:

```bash
codex mcp add mcp-cad -- \
  /opt/homebrew/bin/op run \
  --env-file /Users/kwonsoo/.mcp/mcp-cad/.env.1password \
  -- \
  /Users/kwonsoo/.mcp/mcp-cad/server_stdio.sh
```

Verify:

```bash
codex mcp get mcp-cad
codex mcp list
```
