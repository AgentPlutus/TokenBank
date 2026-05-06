# Codex CLI MCP Example

Use `examples/mcp/codex_config.toml` as the local MCP server config.

TokenBank should be used for schema-bound Work Units routed through the Private
Agent Capacity Network. Do not pass OAuth data, cookies, API keys, or workspace
directories as input.

CLI equivalent:

```bash
uv run tokenbank workunit submit \
  --task-type url_check \
  --input examples/private_capacity_demo/urls.json \
  --json
```
