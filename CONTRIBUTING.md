# Contributing

TokenBank Phase 0 is a Private Agent Capacity Network. Contributions should
keep the control-plane, worker, policy, routing, verification, and audit
boundaries explicit.

## Local Checks

Run these before opening a pull request:

```bash
uv sync
uv run ruff check .
uv run pytest
uv run tokenbank config validate
uv run tokenbank schemas export
git diff --exit-code -- schemas
```

## Development Rules

- Keep changes scoped to the active work package or issue.
- Use Pydantic DTOs as the source of truth for wire contracts.
- Regenerate committed JSON schemas when DTOs change.
- Keep cost and currency-like values as integer micros.
- Write focused tests with each behavior change.
- Preserve deterministic behavior for policy, routing validation,
  canonicalization, hashing, and verifier checks.
- Do not add external services or runtime dependencies unless the public
  roadmap requires them.

## Security Rules

- Do not commit raw secrets, bearer tokens, cookies, provider credentials, host
  tokens, worker tokens, personal data, local databases, logs, or reports.
- Do not broaden MCP or host-adapter access to recursive workspace reads.
- Do not allow workers to write control-plane business state directly.
- Do not add worker-side direct API model provider calls.
- Do not implement seller mode, payment, payout, settlement, account pools, or
  network-layer connectivity in Phase 0.

## Pull Request Checklist

- `ruff` passes.
- `pytest` passes.
- `tokenbank config validate` passes.
- Schema export is current.
- Public docs do not reference internal planning, research, or handoff files.
- New behavior has focused tests.
