# Security Model

TokenBank Phase 0 is a Private Agent Capacity Network with explicit red gates.
The security model is conservative: fail closed, redact secrets, and route all
work through Work Unit state transitions.

## Red Gates

The next phase is blocked if any of these occur:

- raw credential appears in logs, reports, fixtures, JSONL, or event_outbox
- worker direct API model call
- L1/L2 route without `verifier_recipe_id`
- quarantine triggers automatic fallback
- worker directly updates WorkUnit state
- accepted result lacks `output_hash` or `result_hash`
- HostAdapter recursively reads a workspace
- critical state transition lacks an `event_outbox` row
- `capacity_nodes` drifts from worker/backend manifests

## Credential Boundary

Raw secrets, bearer tokens, OAuth tokens, cookies, API keys, provider
credentials, account credentials, and subscription credentials must not be
stored in WorkUnit, RoutePlan, Assignment, ResultEnvelope, VerifierReport,
HostResultSummary, CostQualityReport, event_outbox, JSONL, reports, docs, or
fixtures.

Control-plane gateway stubs never serialize provider tokens. Workers must not
call API model providers directly. The HostAdapter rejects credential-shaped
input.

## HostAdapter And MCP

HostAdapter accepts explicit references only. It must not scan workspace
directories recursively, read `.env`, read secret files, expose workspace
resources over MCP, or act as a model proxy.

MCP remains a bounded stdio stub. It submits schema-bound Work Units;
it does not expose chat completions, responses, or OpenAI-compatible endpoints.

## Network Boundary

The Tailscale analogy is architecture-only. TokenBank does not implement
network-layer connectivity, P2P, relay, WireGuard, NAT traversal, VPN setup, or
transport replacement.
TokenBank does not implement P2P networking.

## Product Boundary

TokenBank Phase 0/1 does not implement seller mode, marketplace, payment,
payout, settlement, account-sharing, OAuth sharing, cookie sharing, API-key
sharing, or active AI plan yield. AI plan yield is Phase 2+ strategy.
