# Ledger And Audit

TokenBank Phase 0 is a Private Agent Capacity Network. WP-LEDGER1 adds local
account snapshots, usage ledger entries, and redacted audit receipts so a host
can inspect private-capacity usage without turning TokenBank into a marketplace,
payment system, or model proxy.

## Objects

- `AccountSnapshot` records local provider/account visibility, balance hints,
  rate-limit hints, and visible model ids. It stores a local secret reference
  only, never the credential value.
- `UsageLedgerEntry` records completed WorkUnit usage and cost evidence. It
  keeps estimated usage separate from provider-reported usage.
- `AuditReceipt` records a hash-backed chain from WorkUnit to RoutePlan,
  Assignment, ResultEnvelope, VerifierReport, and optional UsageLedgerEntry.
  It exports ids and hashes only.

## Commands

```bash
uv run tokenbank accounts snapshot --provider openai --account-label personal --secret-ref keychain:tokenbank/provider/personal --available-micros 25000000 --json
uv run tokenbank accounts refresh --json
uv run tokenbank accounts list --json
uv run tokenbank usage record --work-unit-id <work_unit_id> --json
uv run tokenbank usage ledger --work-unit-id <work_unit_id> --json
uv run tokenbank audit receipt --work-unit-id <work_unit_id> --json
uv run tokenbank audit list --work-unit-id <work_unit_id> --json
```

`accounts refresh` is local-only in WP-LEDGER1. It does not call provider APIs.

## Security Boundary

Ledger and audit tables must not contain raw credentials, bearer tokens,
OAuth tokens, cookies, provider credentials, raw prompts, or raw outputs.
Receipts are designed for local dashboard and audit use: they prove which
control-plane objects were involved by hash, while keeping the private payload
out of the exported receipt.
