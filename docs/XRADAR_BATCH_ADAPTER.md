# x-radar Batch Adapter

x-radar is optional workload source for TokenBank. It is not the core product,
not a host agent, not a multi-agent dependency, and not required for the Private
Capacity Demo.

The optional adapter is deferred in the current implementation. If implemented
later, it must convert selected x-radar posts, URLs, source candidates, or text
batches into schema-bound Work Unit drafts and submit them through
HostAdapterCore.

## Required Boundary

The adapter must not:

- execute work directly
- bypass HostAdapterCore
- bypass Router, Policy, Scheduler, Worker, BackendAdapter, or Verifier
- introduce seller, marketplace, payment, payout, settlement, account-sharing,
  or yield behavior
- request OAuth tokens, cookies, API keys, or account credentials
- expose OpenAI-compatible proxy endpoints

## Expected Deferred Flow

When selected in a later package, the adapter should:

1. Load an explicit batch manifest.
2. Validate privacy and data-label defaults conservatively.
3. Run secret-scan checks before submission.
4. Create Work Unit drafts for known task types only.
5. Submit through HostAdapterCore.
6. Export `source_item_id` to `work_unit_id` and HostResultSummary mappings.

The core Private Agent Capacity Network demo must pass when this adapter is
absent or disabled.
x-radar is not required for the core private capacity demo.
