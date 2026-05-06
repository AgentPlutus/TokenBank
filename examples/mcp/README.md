# TokenBank MCP P0 Stub

TokenBank exposes the Private Agent Capacity Network as nine schema-bound MCP
tools:

- `tokenbank_list_capabilities`
- `tokenbank_estimate`
- `tokenbank_submit`
- `tokenbank_get_result`
- `tokenbank_cancel`
- `tokenbank_get_routebook_excerpt`
- `tokenbank_get_route_explanation`
- `tokenbank_get_task_analysis`
- `tokenbank_get_route_score`

The server is a Phase 0 stdio stub:

- submit Work Units, not chat completions
- no workspace resources or recursive file reads
- no OAuth, cookies, API keys, or provider credentials
- no model proxy behavior

Run locally:

```bash
uv run tokenbank mcp serve
```
