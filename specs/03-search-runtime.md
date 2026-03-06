# Search Runtime

## Core Idea

Argus must treat reasoning as search over candidate states. A candidate is not just a title string. It is a structured object with mechanism, assumptions, failure modes, and unknowns.

## Required Domain Models

### ProblemSpec

Must contain:

- raw user request
- normalized constraints
- success criteria
- optional context metadata

### Candidate

Must contain:

- thesis
- mechanism
- assumptions
- strengths
- failure modes
- unknowns
- optional implementation shape
- evidence references

### ScoreVector

Must contain:

- hard-constraint pass flag
- hard-constraint reasons
- distinctiveness
- usefulness
- specificity
- plausibility
- implementation tractability
- upside
- adversarial robustness
- evidence quality
- total score
- confidence estimate

### Critique

Must contain:

- hidden dependencies
- kill shots
- sharp edges
- summary

### Node

Must contain:

- stable node id
- parent ids
- depth
- action type
- provider name
- candidate
- optional score
- optional critique
- novelty score
- lifecycle status
- metadata
- creation timestamp

### LearningNote

Must contain:

- note type
- text
- source node ids

### SearchState

Must contain:

- problem spec
- root id
- node map
- archive ids
- frontier ids
- pruned ids
- winner ids
- learning notes
- budget spent
- step count

## Action Library

The first version must support these actions:

- `frame_problem`
- `generate_seed`
- `mutate`
- `combine`
- `stress_test`
- `deepen`
- `rank`
- `compress_learning`

These actions are the control vocabulary for the search runtime.

## Required Search Flow

### Version 1 Search Policy

The first working policy should be intentionally simple:

1. frame the problem
2. generate 8 to 12 seed candidates
3. prune hard failures
4. apply novelty filtering
5. stress-test the top 5
6. deepen the top 3
7. optionally mutate or combine top survivors
8. compile the final answer package

### Node Admission Rules

When a provider returns a candidate:

1. validate the response against schema
2. convert the raw payload into typed models
3. calculate novelty against archived nodes
4. reject near-duplicates for generative actions
5. compute the deterministic score vector
6. update router stats
7. persist the node and its attachments

## Concurrency Requirement

The runtime may execute independent provider calls concurrently when doing so reduces wall-clock latency, but it must preserve deterministic state transitions.

That means:

- framing and final persistence may remain serial
- independent stress tests, deepens, mutations, and evaluations may be dispatched concurrently
- provider concurrency must be bounded explicitly, not unbounded
- node ids and persisted artifact layout must remain stable even when provider calls finish out of order
- admission must commit in deterministic order after results are collected

## Novelty Safety Under Concurrency

Naive parallel novelty admission is not acceptable. If multiple candidates from the same batch are processed concurrently, the runtime must prevent two near-duplicates from being admitted just because they both compared against the same stale archive snapshot.

Acceptable approaches include:

- evaluate against a fixed archive snapshot, then run deterministic intra-batch dedupe before commit
- serialize only the final novelty admission step while still parallelizing other expensive calls
- another explicit policy that preserves archive consistency and is covered by tests

Latency reduction is a valid optimization target. Token cost reduction is related but separate, and should not be claimed unless the implementation actually reduces provider work.

## Frontier Strategy

The system must not only expand the single highest-score node. It must preserve stepping stones. Frontier selection should balance:

- current score
- novelty
- depth exploration
- uncertainty or low-confidence opportunities

## Final Answer Compilation

The search runtime must compile the final answer from the archive, not from an ad hoc final provider response. The final answer must include:

- `best_bet`
- `conservative_option`
- `high_upside_option`
- `rejected_but_insightful`
- `summary_markdown`
- `next_experiments`

## Termination Conditions

The search must stop when:

- budget is exhausted
- the frontier is empty
- or the system has a stable winner set that satisfies the configured stop criteria

The exact stop policy can evolve, but it must be explicit and testable.
