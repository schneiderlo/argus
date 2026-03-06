# Evaluator And Ranking

## Principle

The evaluator is the product moat. Generation matters, but evaluation matters more. Argus must prefer a strong, inspectable evaluator over a flashy generator.

## Hard Constraints

Before any weighted score is calculated, a candidate must be checked against hard constraints derived from the problem. Hard constraint failure must:

- mark the node as failed for winning purposes
- record explicit reasons
- make the failure visible in stored state

## Score Dimensions

The initial provider-backed evaluator must produce a vector with these dimensions:

- distinctiveness
- usefulness
- specificity
- plausibility
- implementation tractability
- upside
- adversarial robustness
- evidence quality

The weighting and rubric can evolve, but the first version must be explicit in code, schema-validated, and covered by tests.

## Prompt Design Requirement

The evaluator must not rely on a thin generic wrapper prompt alone. Each evaluation action must materialize an action-specific prompt that tells the provider:

- what role it is performing
- which evidence is authoritative
- how to apply hard constraints
- how to distinguish substance from style
- how to score each rubric dimension
- which failure patterns to look for
- what output shape and level of explanation are required

At minimum, `evaluate_candidate`, `assess_novelty`, and pairwise `rank` comparisons must have their own prompt instructions instead of sharing only a generic provider wrapper.

## Ranking Behavior

Argus must support:

- score-based sorting
- pairwise comparison over a small finalist pool rather than only a single top-two refinement
- different selection logic for best, conservative, and high-upside outputs

The "best overall" answer must not always be identical to the most conservative or highest-upside answer.

## Adversarial Evaluation

Stress testing is mandatory. The system must explicitly try to surface:

- hidden dependencies
- unstated assumptions
- operational pain
- false comparisons against weak baselines
- reasons the candidate could fail in real use

The evaluator prompt should make these adversarial checks explicit rather than assuming the provider will infer them from a generic rubric blob.

## Confidence

The evaluator must output a confidence value. This does not mean subjective certainty. It means the system's belief that the current evidence and structure justify the weighted total.

## Reward For Routing

Provider-routing rewards should be derived from downstream usefulness, not provider self-description. At minimum, the first implementation should reward:

- admitted nodes
- strong scores
- useful critiques
- survivors after stress testing
- nodes that contribute to the final winner set

## Novelty

Novelty must be judged semantically, not primarily through lexical overlap. Cheap deterministic similarity checks are acceptable only as prefilters or guardrails. The decision about whether two candidates are materially the same should come from a provider-backed structured novelty assessment.

The novelty prompt must explicitly define what counts as a near-duplicate, a trivial rephrasing, a shared tactic with different strategic framing, and a genuinely distinct approach. Without those criteria, semantic novelty decisions are too unstable to trust.

## Pairwise Comparison

Pairwise ranking must use a dedicated comparison prompt that asks the provider to compare two candidates against the problem spec and explain the decisive tradeoffs. It must not be implemented as a repackaged scalar score request with different JSON output.

Finalist selection should not stop after comparing only the top two pre-ranked nodes. The runtime should pre-rank candidates to bound cost, then run a bounded round-robin style tournament over a small finalist pool so a slightly lower pre-ranked candidate can still win on direct pairwise merit.

## Benchmark Requirements

The evaluator must be benchmarked against stored prompts. Benchmark cases must cover multiple problem families and record structured outputs so regressions can be detected.

Benchmark coverage must include at least:

- obvious hard-constraint violations that should fail
- paraphrased duplicates that should not pass novelty review
- distinct strategies with overlapping vocabulary that should remain novel
- pairwise comparisons where the higher-quality option is clear
- cases where the conservative option should differ from the highest-upside option

The benchmark suite must assert judgment quality, not only schema conformance or command success.
