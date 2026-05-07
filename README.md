# TokenBank

[![CI](https://github.com/AgentPlutus/TokenBank/actions/workflows/ci.yml/badge.svg)](https://github.com/AgentPlutus/TokenBank/actions/workflows/ci.yml)

TokenBank Phase 0 is a **Private Agent Capacity Network**.

It is the control-plane skeleton for making trusted private agent capacity
callable, routable, policy-governed, verifiable, and measurable. The current
implementation includes the WP0 runnable package frame, WP1 schema/DTO/
canonicalization layer, and WP2 SQLite/event-outbox/capacity-registry
foundation, plus WP3 static config, deterministic policy checks,
cross-registry validation, WP4 authenticated FastAPI control-plane endpoint
skeletons, WP5 scheduler-owned assignment leases, WP6 foreground worker
plumbing for assignment-bound local_tool execution, and WP7 backend/capacity
registry resolution metadata, and WP8 routebook-backed RoutePlan generation.
It also includes WP9 backend adapter scaffolds and ResultEnvelope building for
P0 backend classes, plus WP10 deterministic verifier recipes and VerifierReport
generation. VS0 proves the first url_check end-to-end path from host submission
through worker execution, verification, and HostResultSummary. VS1a extends the
same proven pipeline to dedup through the worker-local local_script backend.
VS1b extends it to webpage_extraction through the worker-local browser_fetch
backend using explicit static input and untrusted-content tagging.
VS1c extends it to topic_classification through the control-plane
api_model_gateway deterministic stub without external provider calls.
VS1d extends it to claim_extraction through the same control-plane gateway and
deterministic claim stub. WP11 adds derived observability and cost/quality
memory reports over persisted objects without making reports the source of
truth. WP12 adds HostAdapterCore and a bounded MCP stdio stub. WP13 adds the
private capacity demo runner. WP-RB1 adds Routebook V1 TaskProfile,
CapacityProfile, and RouteDecisionTrace contracts plus read-only route
explanation through CLI/MCP without changing Phase 0 route selection. WP-RB2
adds deterministic TaskAnalysisReport generation, token/cost estimates,
privacy preflight, `route analyze`, and MCP task analysis without scheduling or
model calls. WP-RB3 adds deterministic RouteScorer hard filters, weighted
candidate scoring, `route score`, MCP route scoring, and scored RoutePlan
selection without scheduling or model calls. WP-LEDGER1 adds local account
snapshots, usage ledger entries, and redacted audit receipts so completed
private-capacity work can be audited without storing raw credentials, prompts,
or outputs. WP-DASH1 adds a local read-only usage/account/audit dashboard,
authenticated dashboard JSON endpoints, and redacted dashboard export. It does
not implement a cloud dashboard, full model gateway runtime, real external
model calls, multi-provider gateway, or peer negotiation.

## Current Scope

The current foundation provides:

- A `uv` Python project.
- A minimal installable `tokenbank` package under `src/`.
- A Typer CLI entry point.
- Pytest and Ruff configuration.
- Phase 0 terminology documentation for the Private Agent Capacity Network.
- Pydantic DTOs as the implementation source of truth.
- Generated JSON Schema artifacts as committed wire contracts.
- Deterministic canonicalization and hashing helpers.
- SQLite bootstrap with WAL, busy timeout, and foreign key pragmas.
- Raw SQL migrations for core tables, capacity node projection, and event outbox.
- Atomic event_outbox writes and JSONL flushing.
- Capacity node registry projection from worker/backend manifests.
- Static YAML config skeletons and runtime mode loading.
- Deterministic WP3 policy checks and cross-registry validation.
- FastAPI app bootstrap with config validation, DB initialization, health,
  authenticated host/worker/internal endpoint skeletons, and capacity discovery.
- Scheduler-owned ExecutionAttempt and Assignment lease transitions, including
  accept, reject, progress, retry/fallback stubs, lease sweeping, result handoff
  stubs, and late-result quarantine.
- A foreground worker runtime with YAML config loading, registration,
  heartbeat, own-assignment polling, accept/progress/result submission,
  completed-result spool replay, redacted logs, and sandbox directory creation.
- Backend manifest loading, backend registry persistence, capacity projection
  validation, and backend intent resolution to worker-local or control-plane
  gateway capacity metadata.
- Routebook YAML for the five P0 task types, task-level classification,
  candidate generation, RoutePlan normalization, RoutePlan validation, and
  RouterService output that stops at RoutePlan.
- BackendAdapter interface, local_tool url_check execution, local_script dedup
  scaffold, browser_fetch egress-deny scaffold, API/primary model gateway
  credential-boundary scaffolds, usage records, normalized backend errors, and
  ResultEnvelope hashes.
- Verifier recipe loading, common integrity/hash/policy/schema/secret checks,
  five deterministic P0 verifier recipes, sampled audit flag scaffolding, and
  Scheduler-consumable VerifierReport recommendations.
- Minimal VS0 host CLI/API glue for `url_check`, including WorkUnit creation,
  RoutePlan generation, PolicyDecision persistence, Scheduler assignment,
  worker-local LocalToolAdapter execution, VerifierReport persistence, and
  HostResultSummary generation.
- Minimal VS1a host CLI/API glue for `dedup`, using the same RoutePlan,
  PolicyDecision, Scheduler, Assignment, Worker, ResultEnvelope, VerifierReport,
  and HostResultSummary path with worker-local local_script execution.
- Minimal VS1b host CLI/API glue for `webpage_extraction`, using the same
  private-capacity path with worker-local browser_fetch execution, explicit
  static HTML/text input, untrusted-content tagging, and `webpage_extraction_v0`
  verification.
- Minimal VS1c host CLI/API glue for `topic_classification`, using the same
  RoutePlan, PolicyDecision, Scheduler, Assignment, ResultEnvelope,
  VerifierReport, and HostResultSummary path through `wrk_control_plane_gateway`
  and a deterministic `api_model_gateway` stub.
- Minimal VS1d host CLI/API glue for `claim_extraction`, using the same
  control-plane gateway path with deterministic structured claims,
  `source_post_refs`, output/result hashes, and `claim_extraction_v0`
  verification.
- WP11 derived CostQualityReport generation, capacity-node performance
  summaries, task/backend/worker summaries, baseline caveats, primary fallback
  cost separation, event_outbox query summaries, metadata-only reproducibility
  refs, and report redaction.
- WP12 HostAdapterCore, schema-bound Work Unit CLI, and bounded MCP stdio
  server that exposes only host-safe tools and no workspace resources.
- WP13 Private Capacity Demo runner over the five supported P0 task types.
- WP-RB1 Routebook V1 compatibility scaffold: ontology pack,
  TaskProfile/CapacityProfile/RouteDecisionTrace DTOs and schemas, deterministic
  TaskProfiler, host-safe route explanations, and MCP route explanation tool.
- WP-RB2 deterministic TaskAnalyzer, TokenEstimate, CostEstimate, InputShape,
  PrivacyScan, ComplexityEstimate, TaskAnalysisReport schema, CLI route
  analysis, MCP task analysis, and route explanations that carry analysis hash
  and estimate summary.
- WP-RB3 deterministic RouteScorer, scoring weights, hard filter decisions,
  weighted score components, RouteScoringReport schema, CLI route scoring, MCP
  route scoring, and RoutePlan selection by highest-scoring passing candidate.
- WP-LEDGER1 AccountSnapshot, UsageLedgerEntry, and AuditReceipt DTOs and
  schemas, SQLite tables, local account snapshot CLI, usage ledger CLI, audit
  receipt CLI, and hash-backed redacted evidence chains for accepted results.
- WP-DASH1 local read-only dashboard data service, localhost HTML dashboard,
  host-authenticated dashboard JSON endpoints, CLI summary/export/serve
  commands, capacity/account/usage/route/receipt sections, and redacted export.
- Smoke tests for importability, CLI help, terminology, schema parity,
  validation, canonical hashing, database bootstrap, event outbox, capacity
  registry, policy, config validation, API auth/startup, scheduler assignment
  state, late-result quarantine, worker polling, worker spool replay, worker
  sandbox creation, backend registry loading, backend/capacity resolution, and
  routebook-backed RoutePlan validation, backend adapter envelopes, credential
  serialization boundaries, verifier recipe reports, quarantine semantics, and
  endpoint drift, plus the VS0 `url_check`, VS1a `dedup`, VS1b
  `webpage_extraction`, VS1c `topic_classification`, VS1d
  `claim_extraction` end-to-end paths, WP11 report generation/redaction, WP12
  MCP tools, WP13 private capacity demo, WP-RB1 route explanation, WP-RB2
  task analysis, WP-RB3 route scoring, and WP-LEDGER1 account/usage/audit
  surfaces, and WP-DASH1 dashboard redaction/API/CLI surfaces.

## Quickstart

```bash
uv sync
uv run tokenbank --help
uv run tokenbank schemas export
uv run tokenbank config validate
uv run tokenbank daemon start --smoke-test
uv run tokenbank host url-check https://example.com/status
uv run tokenbank host dedup '["alpha","beta","alpha"]'
uv run tokenbank host webpage-extract https://example.com/page --html '<html><title>Example</title><body>Data only.</body></html>'
uv run tokenbank host topic-classify 'The API worker stores software cost evidence.' --allowed-labels-json '["engineering","science","finance","policy","general"]'
uv run tokenbank host claim-extract 'TokenBank routes private capacity through a control-plane gateway.' --source-id src_claim_1 --entity TokenBank
uv run tokenbank route analyze --task-type url_check --input tests/fixtures/route_requests/url_check.json --json
uv run tokenbank route score --task-type claim_extraction --input tests/fixtures/route_requests/claim_extraction.json --json
uv run tokenbank route explain --task-type url_check --input tests/fixtures/route_requests/url_check.json --json
uv run tokenbank report summary --run-id <run_id> --json
uv run tokenbank report capacity --run-id <run_id> --json
uv run tokenbank accounts snapshot --provider openai --account-label personal --secret-ref keychain:tokenbank/provider/personal --available-micros 25000000 --json
uv run tokenbank accounts list --json
uv run tokenbank usage record --work-unit-id <work_unit_id> --json
uv run tokenbank usage ledger --work-unit-id <work_unit_id> --json
uv run tokenbank audit receipt --work-unit-id <work_unit_id> --json
uv run tokenbank dashboard summary --json
uv run tokenbank dashboard export --output .tokenbank/dashboard_export.json --json
uv run tokenbank dashboard serve --host 127.0.0.1 --port 8766
uv run tokenbank capacity list
uv run tokenbank mcp serve
uv run pytest
uv run ruff check .
```

With a control-plane daemon running, a foreground worker can be started with:

```bash
uv run tokenbank worker run --config examples/private_capacity_demo/workers/wrk_win_01.yaml
```

## Phase 0 Boundary

TokenBank Phase 0 is not a public capacity exchange, payment product,
credential-sharing layer, network tunnel, or model-provider compatibility
server. Later work packages must preserve this implementation order:

```text
WP0 Repo Bootstrap
WP1 Schemas, DTOs, Canonicalization
WP2 DB, Event Outbox, Capacity Registry
WP3 Config, Policy, Cross-Registry Validator
WP4 Control Plane API
WP5 Scheduler / Assignment
WP6 Worker Daemon
WP7 Capability Registry + Backend Registry
WP8 Router + Routebook
WP9 Backend Adapters
WP10 Verifier Recipes
VS0 url_check E2E
VS1a dedup E2E
VS1b webpage_extraction E2E
VS1c topic_classification E2E
VS1d claim_extraction E2E
WP11 Observability + Cost/Quality Memory
WP12 HostAdapter CLI + bounded MCP stdio stub
WP13 Private Capacity Demo
WP-RB1 Routebook V1 Profiles And Explanation
WP-RB2 TaskAnalyzer And TokenEstimate
WP-RB3 RouteScorer
WP-LEDGER1 Account Ledger And Audit Receipts
WP-DASH1 Local Usage Account Audit Dashboard
then WP-RB4 or later only with an explicit work package
```

Do not proceed to all five task types until VS0 passes.
After WP-DASH1, do not broaden into x-radar, real external model calls, peer
negotiation, cloud dashboard, or multi-provider gateway without an explicit
work package.

## Contributing And Security

See `CONTRIBUTING.md` for local checks and pull request expectations. See
`SECURITY.md` for vulnerability reporting and Phase 0 red gates.

This repository is licensed under the MIT License.
