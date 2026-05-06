# Workload Sources

TokenBank Phase 0 is a Private Agent Capacity Network.

Workload sources create explicit Work Unit requests for the Private Agent Capacity
Network. They do not execute work, do not bypass Router/Policy/Scheduler/Verifier,
and do not read arbitrary workspace contents.

## Current Sources

- HostAdapter CLI: submits explicit JSON, URL, or inline text inputs.
- MCP stdio stub: exposes eight bounded tools that submit Work Units or read
  host-safe summaries.
- Private Capacity Demo: fixture-backed dataset for the five P0 task types.

## Optional Sources

x-radar is optional workload source only. It can be adapted into Work Unit
drafts when explicitly selected, but it is not a multi-agent dependency and is
not required for the Private Capacity Demo.

## Input Rules

Workload sources may accept only explicit file paths, explicit URLs, inline
text, or explicit TokenBank artifact refs. They must not scan a workspace
recursively, expand broad globs, read `.env` files, read secret stores, or
accept OAuth tokens, cookies, API keys, account credentials, or credential
brokers.

## Product Boundaries

Workload sources do not create seller mode, marketplace, payment, payout,
settlement, account-sharing, or AI plan yield flows. AI plan yield is Phase 2+
strategy and is not active in Phase 0/1.
