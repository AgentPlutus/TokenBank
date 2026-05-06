# Security Policy

TokenBank is an early Phase 0 Private Agent Capacity Network implementation.
Please treat security boundaries as part of the product contract, not as
optional examples.

## Supported Versions

The public repository currently supports only the `main` branch. There are no
published production releases yet.

## Reporting A Vulnerability

Do not open a public issue that includes secrets, exploit details, host tokens,
private worker data, or provider credentials.

Use GitHub's private vulnerability reporting flow for this repository if it is
available. If that flow is not available, contact the maintainers privately
through the AgentPlutus GitHub organization before publishing details.

Include:

- A concise description of the issue.
- Steps to reproduce with synthetic data only.
- Whether the issue can expose raw credentials, mutate WorkUnit state, bypass
  policy, create an unverified L1/L2 route, or cause quarantine auto-fallback.
- The commit SHA and runtime mode used during testing.

## Phase 0 Red Gates

These are release blockers:

- Raw credential appears in a log, report, fixture, event, or test output.
- Worker can directly call an API model provider.
- L1/L2 route is created without a verifier recipe.
- Quarantine triggers automatic fallback.
- Worker directly updates WorkUnit business state.
- Accepted result lacks output/result hash.
- Host adapter recursively reads a workspace.
- State transition is committed without an event_outbox row.
- Capacity node projection drifts from worker/backend manifests.

## Handling Secrets

Never submit real API keys, bearer tokens, cookies, provider credentials,
private host tokens, worker tokens, or personal data in issues, pull requests,
fixtures, test snapshots, logs, or reports.
