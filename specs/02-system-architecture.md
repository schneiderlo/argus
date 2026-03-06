# System Architecture

## Implementation Language

The first implementation must use Python 3.12. The system should prefer the standard library and small, well-justified dependencies.

## Package Management

The project must use `uv` as the package manager and environment runner. The initial scaffold should therefore be compatible with commands such as `uv sync`, `uv run pytest`, and `uv run argus ...`.

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

### Storage

Storage must be filesystem-backed at first. It must persist:

- run metadata
- node objects
- score vectors
- critiques
- learning notes
- benchmark outputs
- final compiled recommendations

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

### Evaluator

The evaluator must be deterministic first. Pairwise or LLM-assisted judging can be layered on later, but the first version must not depend on an opaque model-based rubric just to function.

### Provider Layer

The provider layer must expose a single interface for running actions and returning schema-validated structured data. Codex is the first provider and the main supported provider.

## Architecture Constraints

- provider outputs must be validated before entering state
- the app must be able to replay a run from stored artifacts
- no provider may write arbitrary repo files as part of its output contract
- state must be inspectable with normal shell tools
- failures must be explicit and serializable
