# MCP Server

TokenBank provides a Phase 0 MCP stdio stub for the Private Agent Capacity
Network, the Phase 0 Private Agent Capacity Network product surface.

Run:

```bash
uv run tokenbank mcp serve
```

## Tool Surface

The MCP server exposes exactly eight bounded tools:

- `tokenbank_list_capabilities`
- `tokenbank_estimate`
- `tokenbank_submit`
- `tokenbank_get_result`
- `tokenbank_cancel`
- `tokenbank_get_routebook_excerpt`
- `tokenbank_get_route_explanation`
- `tokenbank_get_task_analysis`

`tokenbank_submit` creates schema-bound Work Units through HostAdapterCore. It
does not execute Work Units directly and does not bypass Router, Policy,
Scheduler, Worker, BackendAdapter, or Verifier.

`tokenbank_get_route_explanation` is the WP-RB1 Routebook V1 read-only
explanation tool. It returns a TaskProfile, CapacityProfile summaries, a
RouteDecisionTrace, TaskAnalysisReport, and the existing RoutePlan without
scheduling or executing work.

`tokenbank_get_task_analysis` is the WP-RB2 deterministic preflight tool. It
returns InputShape, TokenEstimate, CostEstimate, PrivacyScan,
ComplexityEstimate, effective risk/privacy levels, and a stable analysis hash
without calling a model.

## Resource Boundary

The Phase 0 server does not expose workspace resources. `resources/list` and
`resources/read` are closed in this stub. MCP must not read arbitrary files,
scan directories recursively, save OAuth tokens, save cookies, save API keys, or
store account credentials.

## Not A Model Proxy

The MCP server is not an OpenAI-compatible model proxy. It does not implement
chat completions, responses, streaming model APIs, provider credential
forwarding, or final-answer writing. It submits Work Units to private capacity
and returns host-safe summaries.

## Caveats

The current server is a P0 validation stub. It is suitable for local private
capacity demos and adapter validation, not public alpha deployment without the
hardening listed in `docs/PUBLIC_ALPHA_PACKAGE.md`.
