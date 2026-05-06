# Routebook

This routebook is the WP8 routing contract for TokenBank Phase 0, the Private
Agent Capacity Network.

WP-RB1 implements the compatibility scaffold under
`packs/base-routing/routebook/`, and WP-RB2 adds deterministic task analysis and
token/cost/privacy estimates. These layers do not replace this Phase 0 route
selection contract.

It maps the five P0 work-unit task types to route candidates and verifier
recipes. The router may read these files to produce a `RoutePlan` only. It must
not execute work, create `ExecutionAttempt`, create `Assignment`, call backend
adapters, call a model gateway, mutate WorkUnit state, or persist hidden
chain-of-thought.

Worker-local route classes are `local_tool`, `local_script`, and
`browser_fetch`. API model gateway classes must resolve to
`wrk_control_plane_gateway`, never to a Windows worker direct API-model path.
