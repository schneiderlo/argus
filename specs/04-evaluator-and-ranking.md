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

## Ranking Behavior

Argus must support:

- score-based sorting
- pairwise comparison later
- different selection logic for best, conservative, and high-upside outputs

The "best overall" answer must not always be identical to the most conservative or highest-upside answer.

## Adversarial Evaluation

Stress testing is mandatory. The system must explicitly try to surface:

- hidden dependencies
- unstated assumptions
- operational pain
- false comparisons against weak baselines
- reasons the candidate could fail in real use

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

## Benchmark Requirements

The evaluator must be benchmarked against stored prompts. Benchmark cases must cover multiple problem families and record structured outputs so regressions can be detected.
