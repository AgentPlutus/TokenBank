# Capability Nodes

Capability nodes are the host-safe projection of private capacity in TokenBank
Phase 0. They describe what trusted worker and backend capacity can do without
exposing raw worker manifests, secrets, logs, or provider credentials.

## Source Of Truth

`capacity_nodes` is a projection over worker manifests and backend manifests.
It is not an independent source of truth. Rebuilds must remove stale capacity
nodes and keep worker/backend manifest identity, backend ids, backend classes,
allowed task types, health status, and manifest hashes aligned.

The cross-registry validator rejects drift between:

- `config/capacity_registry.yaml`
- `config/backend_registry.yaml`
- `config/backend_policy.yaml`
- routebook backend classes and verifier recipes
- worker manifests and backend ids

## Worker And Gateway Nodes

Worker-local capacity can resolve `local_tool`, `local_script`, and
`browser_fetch` backends. API model gateway and primary model gateway routes
resolve to the control-plane pseudo-worker `wrk_control_plane_gateway`; Windows
workers must not call API model providers directly.

## Boundaries

Capability discovery is not a seller marketplace and not a yield surface. It
does not advertise payouts, settlement, payments, public exchange inventory, or
account-sharing capacity. It is a private capability map for schema-bound Work
Units inside the Private Agent Capacity Network.
