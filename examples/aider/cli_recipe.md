# Aider CLI Recipe

Use TokenBank through CLI commands, not through a model-proxy endpoint.

Run one private capacity demo task:

```bash
uv run tokenbank demo capacity run --task url_check --json
```

Run all five Phase 0 demo tasks:

```bash
uv run tokenbank demo capacity run --all --json
```

Submit one explicit Work Unit:

```bash
uv run tokenbank workunit submit \
  --task-type url_check \
  --input examples/private_capacity_demo/urls.json \
  --json
```

Do not pass workspace directories, OAuth tokens, cookies, API keys, account
credentials, seller/marketplace instructions, or yield claims as Work Unit
input.
