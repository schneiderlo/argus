# Archive And Novelty

## Purpose

The archive is what prevents Argus from behaving like a forgetful chat session. Every serious candidate and critique must become part of persistent searchable state.

## Archive Contents

The archive must persist:

- every admitted node
- node metadata and parent relationships
- critique payloads
- score vectors
- learning notes
- final recommendations

## Novelty Policy

Generative actions must be checked against the archive before admission. A candidate that is effectively a paraphrase of an existing candidate should be rejected or heavily down-ranked.

The first version should use an embedding-based or text-similarity-based novelty calculation with:

- a stable candidate text projection
- a configurable similarity threshold
- persistence of novelty scores for later analysis

## Learning Compression

Every few steps, the system should compress recent search results into reusable learning notes such as:

- winning patterns
- repeated failure patterns
- high-value constraints
- routing hints

These notes must be first-class stored objects, not only transient prompt text.

## Cross-Run Reuse

Reusable learning notes should survive beyond a single run. The first durable version should:

- maintain a root-level shared learning-memory ledger with note provenance
- deduplicate exact repeated learnings into support-counted entries
- snapshot the subset of imported reusable learnings into each run directory for audit
- feed those imported priors back into future framing, generation, evaluation, ranking, and critique actions

Deterministic retrieval is acceptable for selecting a bounded subset of stored learnings, but it must remain a retrieval layer only, not a replacement for provider-backed evaluation or novelty judgment.

## Replay And Audit

An operator must be able to inspect a run and answer:

- which nodes were created
- why a node was admitted or rejected
- which nodes were pruned
- which nodes contributed to the final answer

That means the archive format must remain human-inspectable.

## Multi-Island Archive Behavior

When multi-island search is enabled, the archive must still behave like one deterministic run-level source of truth. That means:

- admitted nodes keep one global node id and one persisted node record even when islands use different search priors
- the run state also persists explicit per-island archive/frontier/pruned views so the operator can audit how each island evolved
- novelty checks still guard the run-level archive, not only one island, so cross-island duplicates do not silently accumulate

## Future Direction

Later versions should allow selective migration of strong insights between islands without losing the audit trail for which island first produced or adopted a node.
