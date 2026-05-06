# Claude Code MCP Example

Use `examples/mcp/claude_code_mcp.json` as the local server config.

The TokenBank MCP server exposes Private Agent Capacity Network Work Unit tools
only. It does not expose workspace resources, save credentials, or behave as a
model proxy.

Example MCP submit arguments:

```json
{
  "task_type": "url_check",
  "input": {
    "url": "https://example.com/status"
  }
}
```
