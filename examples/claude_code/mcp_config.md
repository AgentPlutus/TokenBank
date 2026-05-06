# Claude Code MCP Config

Use the P0 MCP stdio stub only for schema-bound Work Units.

```json
{
  "mcpServers": {
    "tokenbank": {
      "command": "uv",
      "args": ["run", "tokenbank", "mcp", "serve"]
    }
  }
}
```

This server is not a model proxy and does not expose workspace resources. Do
not configure OAuth tokens, cookies, API keys, or account credentials.
