# Private Agent Capacity Network

TokenBank Phase 0 is a Private Agent Capacity Network. It makes trusted
private agent capacity callable, routable, policy-governed, verifiable, and
measurable across trusted machines.

The Phase 0 product is not a model router, not an OpenAI-compatible model
proxy, not x-radar infrastructure, not a seller marketplace, and not a
financial-yield product.

## Architecture Boundary

The Tailscale analogy is architecture-only: TokenBank wants private capacity to
feel addressable in the same way private machines can be made reachable, but
TokenBank does not implement network-layer connectivity. It does not implement
P2P networking, relay servers, WireGuard, NAT traversal, device VPN setup, or
transport replacement.

TokenBank coordinates Work Units, RoutePlans, PolicyDecisions,
ExecutionAttempts, Assignments, ResultEnvelopes, VerifierReports, and
HostResultSummary objects. Connectivity, secrets, routing, verification, and
cost/quality evidence remain explicit system boundaries.

## Implemented Phase 0 Surface

The current implementation includes:

- WP0 repository bootstrap.
- WP1 Pydantic DTOs, committed JSON Schema artifacts, and canonical hashes.
- WP2 SQLite, raw migrations, event outbox, JSONL flusher, and capacity
  registry projection.
- WP3 runtime config, policy checks, and cross-registry validation.
- WP4 authenticated FastAPI control-plane skeleton.
- WP5 Scheduler-owned attempt, assignment, lease, retry, fallback, and
  quarantine state transitions.
- WP6 foreground worker daemon and sandbox/spool/logging behavior.
- WP7 backend registry, capability registry, and resolver.
- WP8 routebook and RouterService for the five P0 task types.
- WP9 backend adapter scaffolds and local/gateway deterministic execution.
- WP10 verifier recipes for the five P0 task types.
- VS0 through VS1d end-to-end slices for `url_check`, `dedup`,
  `webpage_extraction`, `topic_classification`, and `claim_extraction`.
- WP11 derived Cost / Quality Memory reports.
- WP12 HostAdapter CLI and bounded MCP stdio stub.
- WP13 Private Capacity Demo.
- WP-RB1 Routebook V1 profile contracts and read-only route explanation.
- WP-RB2 deterministic task analysis, token/cost estimate, and privacy
  preflight without scheduling work or calling a model.
- WP-RB3 deterministic route scoring with hard filters, weighted candidate
  scores, stable scoring reports, CLI/MCP route scoring, and scored RoutePlan
  selection without scheduling work or calling a model.

## Non-Goals

TokenBank Phase 0/1 does not implement seller mode, marketplace, payment,
payout, settlement, account-sharing, OAuth sharing, cookie sharing, API-key
sharing, real external model calls, multi-provider gateway runtime, scored
route execution beyond Phase 0 boundaries, peer negotiation, full dashboard UI,
or OpenAI-compatible proxy
endpoints.

AI plan yield is Phase 2+ strategy and is not active in Phase 0/1.

## Workload Sources

HostAdapter CLI and MCP submit schema-bound Work Units. The Private Capacity
Demo is the core demo workload source. x-radar is optional workload source
only; it is not a multi-agent dependency and is not required for the core
private capacity demo.
