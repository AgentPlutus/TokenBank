# Public Alpha Package

Public alpha is not active in Phase 0. This document records the caveats that
must be true before packaging TokenBank for alpha users.

## Required Caveats

TokenBank must be described as a Private Agent Capacity Network. Public alpha
docs must state:

- the Tailscale analogy is architecture-only
- TokenBank does not implement network-layer connectivity
- TokenBank does not expose an OpenAI-compatible model proxy
- TokenBank does not store user OAuth tokens, cookies, API keys, account
  credentials, or subscription credentials
- x-radar is optional workload source and not a multi-agent dependency
- AI plan yield is Phase 2+ strategy and is not active in Phase 0/1
- seller mode, marketplace, payment, payout, settlement, and account-sharing
  are not implemented in Phase 0/1

## Installer Rules

Installers and examples must not request raw API keys, OAuth flows, cookies, or
account credentials. Any token bootstrap flow must display raw TokenBank tokens
only once and store only hashes and prefixes.

## Before Alpha

Before alpha, rerun the security red gates, MCP tool cap tests, docs language
scans, E2E slices, private capacity demo, and Cost / Quality Memory reports.
Any red gate failure blocks alpha packaging.
