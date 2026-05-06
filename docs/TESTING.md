# Testing

TokenBank Phase 0 testing is organized around source-of-truth contracts,
security red gates, and end-to-end private capacity slices.

## Core Commands

```bash
uv run tokenbank schemas export
uv run tokenbank config validate
uv run tokenbank route analyze --task-type url_check --input tests/fixtures/route_requests/url_check.json --json
uv run tokenbank route explain --task-type url_check --input tests/fixtures/route_requests/url_check.json --json
uv run pytest tests/e2e/test_vs0_url_check.py tests/e2e/test_vs1a_dedup.py tests/e2e/test_vs1b_webpage_extraction.py tests/e2e/test_vs1c_topic_classification.py tests/e2e/test_vs1d_claim_extraction.py
uv run pytest tests/e2e/test_private_capacity_demo.py
uv run pytest tests/integration/test_route_analyze_cli.py tests/integration/test_route_explain_cli.py tests/integration/test_mcp_tools.py
uv run pytest
uv run ruff check .
```

## Red Gate Coverage

Security tests must cover:

- no raw credentials in logs, reports, fixtures, event_outbox, or JSONL
- no worker direct API model calls
- no L1/L2 route without verifier recipe
- no quarantine auto-fallback
- no worker direct WorkUnit mutation
- no accepted result without output/result hashes
- no HostAdapter recursive workspace read
- event_outbox rows for critical state transitions
- no capacity node drift from worker/backend manifests

## Docs Scans

Docs tests check that public docs keep Private Agent Capacity Network framing,
describe x-radar as optional workload source only, keep the Tailscale analogy
architecture-only, and do not present seller/yield/marketplace as active Phase
0/1 features.
