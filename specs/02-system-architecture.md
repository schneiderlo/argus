# System Architecture

## Implementation Language

The first implementation must use Python 3.12. The system should prefer the standard library and small, well-justified dependencies.

## Package Management

The project must use `uv` as the package manager and environment runner. The initial scaffold should therefore be compatible with commands such as `uv sync`, `uv run pytest`, and `uv run argus ...`.

The repository may also provide an optional Nix dev shell to provision the
toolchain on Linux/WSL, especially `python3.12`, `uv`, `node`, and `npm`, but
that shell is a host-environment convenience layer only. It must not replace
`uv` as the repository's package manager or normal command runner.

## Package Layout

The target package layout should look like this once implementation begins:

```text
pyproject.toml
src/argus/
  cli.py
  config.py
  models/
  providers/
  search/
  eval/
  storage/
  benchmarks/
  render/
tests/
```

The exact module split can evolve, but the architecture must preserve clean boundaries.

## Major Components

### CLI

The CLI entrypoint must be named `argus`. Initial subcommands should include:

- `argus run` to execute a search for a single request
- `argus benchmark` to execute stored benchmark cases
- `argus feedback` to ingest shipped experiment outcomes for persisted run nodes
- `argus status` to report the latest or selected run's progress and current activity
- `argus inspect` to inspect persisted run artifacts

### Models

The application must define typed representations for:

- `ProblemSpec`
- `Candidate`
- `ScoreVector`
- `Critique`
- `Node`
- `LearningNote`
- `SearchState`
- `FinalRecommendation`

These models are core domain objects, not loose dictionaries.

Argus must also grow a second layer of typed decision-artifact models for the
research-oriented pipeline. The compact `Candidate` object is useful for search
state and evaluator inputs, but it is too lossy to carry full decision work on
its own. The repository should therefore treat the following as first-class
stored objects as the system evolves:

- `SearchSpaceFrame`
- `SearchAxis`
- `SearchCell`
- `CoverageLedger`
- `ProposalBrief`
- `TriageReport`
- `DeepDiveDoc`
- `AdversarialReview`
- `ComparisonMatrix`
- `HybridAssessment`
- `FinalDecisionDoc`

These richer artifact models should remain typed and serializable just like the
core search models. Human-readable markdown may be rendered from them, but the
typed artifact is the source of truth.

### Storage

Storage must be filesystem-backed at first. It must persist:

- run metadata
- node objects
- score vectors
- critiques
- learning notes
- outcome feedback records linked to persisted runs and nodes
- reusable cross-run learning memory with provenance
- benchmark outputs
- final compiled recommendations

As the research pipeline becomes a first-class runtime, storage must also be
able to persist a decision-artifact bundle per run. At minimum that bundle
should support:

- search-space framing artifacts
- coverage-led planning state
- proposal briefs
- triage outcomes
- deep-dive dossiers
- standalone technical dossiers for each deepened proposal when the mechanism
  depends on math, source-domain transfer, implementation hooks, or ablation
  design that would be too lossy as a one-paragraph proposition
- adversarial reviews
- comparison matrices
- hybrid assessments
- final decision documents

The human-readable markdown files are important operator outputs, but they
should be accompanied by structured JSON artifacts so the runtime, benchmarks,
and observer do not need to re-parse prose.

The implementation must favor explicit JSON files and stable paths over hidden or magical state.

### Search Runtime

The runtime must own:

- frontier selection
- action dispatch
- node admission
- novelty filtering
- pruning
- learning compression
- final answer compilation

Providers must not directly own global application state.

Argus should support two closely related runtime modes:

1. a compact search runtime centered on candidate admission, evaluator-backed
   ranking, and archive management
2. a coverage-led research runtime centered on explicit search-space framing,
   family-level coverage, deep artifact authoring, and final decision packages

The research runtime should be the default operator-facing path once it proves
itself on benchmarks. The compact runtime remains valuable as infrastructure,
as a control in benchmarks, and as a helper layer for novelty checks,
evaluation, and bounded branch exploration.

The scheduler and the authoring layer should be separated explicitly:

- the scheduler decides where the next unit of budget goes
- the authoring actions produce high-quality typed artifacts for that decision

This prevents the system from collapsing into either quota-driven prompt
choreography or search mechanics with shallow final writeups.

### Evaluator

The main evaluator must be provider-backed and schema-validated from the start. Deterministic logic is still useful, but only for validation guardrails, explicit hard checks, and other cheap safety rails. It must not be the primary quality judge for strategic ranking.

### Provider Layer

The provider layer must expose a single interface for running actions and returning schema-validated structured data. Codex is the first provider and the main supported provider.

## Architecture Constraints

- provider outputs must be validated before entering state
- the app must be able to replay a run from stored artifacts
- no provider may write arbitrary repo files as part of its output contract
- state must be inspectable with normal shell tools
- failures must be explicit and serializable

Additional constraints for the research-oriented architecture:

- the runtime must not rely on markdown alone as its only semantic memory
- the coverage planner must be explicit and auditable rather than implicit in
  fixed prompt quotas
- hybrids must be gated by a typed seam hypothesis and complexity-tax analysis,
  not by generic pair combination alone
- the final recommendation should come from a dedicated decision-authoring
  stage that reads the full artifact bundle, not only from a summary template
