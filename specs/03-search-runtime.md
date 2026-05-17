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
- optional per-island frontier/archive/pruned state when multi-island search is enabled
- learning notes
- budget spent
- step count

### Research Artifacts

The richer research-oriented runtime must also persist typed artifacts that sit
above individual nodes. These artifacts make search coverage and final
recommendation quality auditable in a way that compressed candidates alone
cannot.

At minimum the runtime must be able to persist:

- a `SearchSpaceFrame` with divergence axes, explicit hard gates, soft criteria,
  baseline options, and a concise coverage plan
- a `CoverageLedger` with cells or candidate families, their coverage status,
  uncertainty, hard-gate risk, and incumbent proposal references
- `ProposalBrief` objects for seeded representatives
- `TriageReport` objects describing eliminations, collapses, survivors, and
  unexplored regions
- `DeepDiveDoc` artifacts for surviving families
- a standalone technical dossier for each deepened family when the decision
  requires mathematical mechanism, implementation-hook, prior-art, or ablation
  detail that would be flattened by a proposal summary
- `AdversarialReview` artifacts for surviving families
- `ComparisonMatrix`, `HybridAssessment`, and `FinalDecisionDoc` artifacts for
  the final decision stage

## Action Library

The first version must support these actions:

- `frame_problem`
- `generate_seed`
- `migrate`
- `mutate`
- `combine`
- `stress_test`
- `deepen`
- `rank`
- `compress_learning`

These actions are the control vocabulary for the search runtime.

The research-oriented path should add a second tier of actions focused on
coverage planning and decision-artifact production. Expected actions include:

- `frame_search_space`
- `seed_cell_proposals`
- `triage_proposals`
- `deepen_family`
- `redteam_family`
- `assess_hybrid`
- `write_final_decision`

These may internally reuse the compact action library, but they should be
visible at the runtime and artifact layer so the operator can inspect what the
system actually did.

## Required Search Flow

### Version 1 Search Policy

The first working policy should still be intentionally simple, but it should already be a frontier loop rather than a one-pass phase script:

1. frame the problem
2. generate an initial seed population
3. prune hard failures and reject near-duplicates on admission
4. refresh a ranked frontier from the archive
5. choose the next action based on frontier state:
   widen with more seeds when diversity collapses,
   stress-test promising but unchallenged nodes,
   deepen under-specified survivors,
   mutate critiqued but repairable branches,
   combine compatible survivors,
   migrate strong source-island ideas into plateaued destination islands when cross-island transfer is justified,
   revisit archived stepping stones when stage capacity is wider than the live frontier,
   or compress learning periodically
6. repeat until the run budget or stop condition is reached
7. compile the final answer package from the resulting archive

### Coverage-Led Research Policy

The richer default runtime should not rely on fixed proposal counts such as
"generate 10" as its main planning primitive. Instead it should:

1. frame the search space explicitly
2. define divergence axes and baseline options
3. build a coverage ledger of important cells or candidate families
4. seed one or more representatives for the highest-value uncovered cells
5. triage at the family level, not only at the individual-proposal level
6. deepen incumbents for the most promising surviving families
   into implementation-ready dossiers that include the underlying mechanism,
   formulas or transferable rules, code hooks, ablation design, prior-art
   collision notes, and verification-needed caveats where relevant
7. red-team incumbents whose value is high but whose uncertainty or fragility is
   still material
8. consider hybridization only when a typed seam hypothesis and repaired
   failure mode justify it
9. stop when marginal information gain is low or the remaining uncovered cells
   are clearly dominated, invalid, or low value
10. write the final decision package from the full artifact bundle

The scheduler should therefore choose the next action from explicit coverage
state, not only from frontier scores.

### Node Admission Rules

When a provider returns a candidate:

1. validate the response against schema
2. convert the raw payload into typed models
3. calculate novelty against archived nodes
4. reject near-duplicates for generative actions
5. compute the evaluator score vector
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

Stage parent selection should sample from the full island archive, not only the current frontier. The strongest current survivors should still get first access to stage work, but additional stage capacity should be able to revisit older archived stepping stones so the search can exploit promising off-frontier branches instead of collapsing onto one narrow beam.

For the research runtime, the analogous rule is that stage selection should not
be driven only by "top proposals so far." It should also account for:

- uncovered but important cells
- families with high uncertainty
- families with unresolved hard-gate risk
- families whose current incumbent is promising but poorly attacked
- dominated regions that can be safely closed

## Multi-Island Search

Later search policies may run multiple search islands with different optimization priors. When enabled, the runtime must:

- keep a single deterministic global node id space and persisted node archive
- maintain explicit per-island archive, frontier, and pruned bookkeeping for audit
- let each island evolve mostly from its own admitted survivors rather than collapsing into one shared frontier
- keep cross-island novelty admission deterministic so two islands cannot race the same near-duplicate into state
- keep migration explicit and auditable so the operator can see which source island and source node inspired a destination-island adoption
- allow the final recommendation to draw winners from different islands while still compiling from persisted state rather than a final ad hoc provider answer

The first multi-island version does not need free-form island creation. A fixed small set of typed optimization priors is acceptable as long as the state and selection logic remain explicit and testable.

## Final Answer Compilation

The search runtime must compile the final answer from the archive, not from an ad hoc final provider response. The final answer must include:

- `best_bet`
- `conservative_option`
- `high_upside_option`
- `rejected_but_insightful`
- `summary_markdown`
- `next_experiments`

When choosing `best_bet`, `conservative_option`, and `high_upside_option`, the runtime should use provider-backed pairwise ranking over a bounded finalist pool rather than relying only on scalar score ordering or a single top-two comparison.

For the research runtime, the final operator-facing answer should come from a
dedicated decision-authoring stage that reads:

- the search-space frame
- the coverage ledger
- the surviving proposal briefs
- the deep-dive dossiers
- the adversarial review
- the comparison matrix
- any justified hybrid assessments

The final recommendation object should still be typed and persisted, but the
user-facing markdown should be rendered from this full decision artifact set
rather than from terse node fields alone.

The runtime must explicitly preserve:

- why the winning family beat neighboring families
- when the runner-up would become preferable
- which option is safest but least exciting
- which option has the highest upside if its assumptions hold
- the top risks and their mitigations
- the first implementation spike and kill criteria
- a compact decision rule for acting under uncertainty

## Hybridization Rule

Hybridization must not be a generic "combine two strong nodes" move. A hybrid is
justified only when all of the following are true:

- the parents solve different important subproblems
- the strengths are complementary rather than redundant
- the seam is concrete enough to describe and audit
- the resulting complexity tax is worth paying
- the hybrid repairs a real failure mode of the best single approach

If these conditions do not hold, the runtime should prefer the best single
family representative.

## Termination Conditions

The search must stop when:

- budget is exhausted
- the frontier is empty
- or the system has a stable winner set that satisfies the configured stop criteria

The exact stop policy can evolve, but it must be explicit and testable.
