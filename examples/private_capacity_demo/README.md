# Private Capacity Demo

This fixture set demonstrates TokenBank Phase 0 as a Private Agent Capacity
Network. It does not require x-radar, does not expose a model proxy, and does
not pass OAuth, cookies, API keys, or provider credentials.

Run one task:

```bash
uv run tokenbank demo capacity run --task url_check --json
```

Run all five task types:

```bash
uv run tokenbank demo capacity run --all --json
```

The JSON output includes submitted Work Units, HostResultSummary objects,
capacity node discovery, and Cost / Quality Memory report summaries. The
`run_id` field can be passed to:

```bash
uv run tokenbank report summary --run-id <run_id> --json
```

Fixtures:

- `urls.json`
- `dedup.json`
- `webpage_extraction.json`
- `topic_classification.json`
- `claim_extraction.json`
- `dataset_manifest.json`
