# EP Route Contract

This file is the implementation-facing contract for `config/route-registry.json`.

Every route must expose `route_required`, `route_started`, `candidates_discovered`,
`returned_to_host`, `delivery_state`, and `unresolved`. User and Agent routes must
bind `prompt_id`, `session_id`, `turn_id`, and `hook_invocation_id` whenever the
route is initiated by a Codex prompt.

The Flow API is read-only. Opening a chain page must never re-run Recall, Research,
Agent Recall, Agent Research, RAG, or a model call. Unbound global records may be
shown only in a separate unassociated-activity view.

`route_receipt` rows are transport projections, not memories, and must be excluded
from future retrieval. Any route that cannot provide a bound receipt must report
`unknown` or `not_observed`, never infer a zero from missing data.

The UI contract is invariant across renderers:

```text
node.candidates == detail.candidate_items.length (when complete)
node.delivered == detail.items.filter(item => item.delivered).length
```

For topology edges, every edge has a stable ID, source, target, kind, real source
and target handles, and a visible marker. The rightmost merge edges are tested
independently; a shared decorative line cannot satisfy the contract.
