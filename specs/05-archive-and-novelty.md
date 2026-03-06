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

## Replay And Audit

An operator must be able to inspect a run and answer:

- which nodes were created
- why a node was admitted or rejected
- which nodes were pruned
- which nodes contributed to the final answer

That means the archive format must remain human-inspectable.

## Future Direction

Later versions should add search islands with different optimization priors and allow selective migration of strong insights between islands.

