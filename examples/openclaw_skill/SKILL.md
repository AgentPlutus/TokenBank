# TokenBank Private Capacity Skill

Use this skill to submit explicit Work Units to TokenBank's Private Agent
Capacity Network.

## Use

- `url_check` for explicit URLs
- `dedup` for explicit JSON arrays
- `webpage_extraction` for explicit URLs or static HTML fixtures
- `topic_classification` for explicit text and allowed labels
- `claim_extraction` for explicit text and source refs

## Commands

```bash
uv run tokenbank demo capacity run --task url_check --json
uv run tokenbank demo capacity run --all --json
uv run tokenbank workunit submit --task-type url_check --input examples/private_capacity_demo/urls.json --json
```

## Boundaries

Do not pass OAuth tokens, cookies, API keys, account credentials, workspace
directories, shell commands, or model-proxy requests. x-radar is optional
workload source only and is not required for this skill.
