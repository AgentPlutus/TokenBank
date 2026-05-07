# Local Dashboard

TokenBank Phase 0 is a Private Agent Capacity Network. WP-DASH1 adds a
local-first, read-only dashboard for account state, usage ledger rows, route
audit evidence, audit receipts, capacity health, and redacted export.

This is not a cloud dashboard and does not upload provider credentials,
prompts, outputs, artifacts, or receipt details to TokenBank-operated
infrastructure.

## Surfaces

- `tokenbank dashboard summary --json` returns the same redacted dashboard
  snapshot used by the local UI.
- `tokenbank dashboard export --output <path> --json` writes a user-controlled
  redacted export with an export hash.
- `tokenbank dashboard serve --host 127.0.0.1 --port 8766` serves the local
  HTML dashboard and `summary.json` / `export.json`.
- `/v0/dashboard/summary` and `/v0/dashboard/export` expose the same data
  through the main control-plane API and require a host token.

## Privacy Contract

Dashboard data is generated from local control-plane SQLite state. Account
secret refs are reduced to kind and status. Usage rows distinguish estimated
usage from provider-reported usage. Receipts render ids and hashes only.

Dashboard responses must not render raw credentials, bearer tokens, OAuth
tokens, cookies, provider credentials, raw prompts, or raw outputs.

## Sections

- Accounts: provider/account labels, configured state, secret-ref kind/status,
  visible models, balance source, balance confidence, rate-limit hints.
- Usage Ledger: WorkUnit id, RoutePlan id, usage source, cost source, billable
  micros, backend id, verifier recommendation.
- Route Audit: selected backend/capacity evidence, verifier recommendation,
  route plan hash, receipt hash.
- Audit Receipts: receipt ids, WorkUnit ids, result hashes, receipt hashes.
- Capacity Health: capacity nodes, backend classes, task types, health summary.
