# Output Artifacts And Benchmarks

## Final Artifacts

A completed `argus run` must persist:

- the normalized problem spec
- the full node archive
- score vectors
- critiques
- learning notes
- any imported reusable-learning context used to steer the run
- the final recommendation object
- a readable markdown summary for humans

The repository should also persist a root-level reusable learning-memory ledger so future non-benchmark runs can reuse compressed patterns with provenance.

## Final Recommendation Requirements

The final recommendation object must include:

- identifiers for the selected nodes
- a human-readable summary
- explicit next experiments
- explicit assumptions and reversal conditions

## Benchmark Dataset

The repository must eventually contain benchmark fixtures that cover:

- product strategy
- growth and retention
- UX and workflow design
- technical architecture
- monetization or go-to-market

Each benchmark case should include:

- input request
- constraints
- evaluation notes or expected qualities
- room for storing Argus outputs

## Benchmark Harness

The benchmark harness must:

- execute stored cases
- persist outputs
- record run metadata
- make regressions visible

To keep comparisons stable, the harness may isolate or disable shared cross-run learning memory while still persisting each case's own run artifacts.

The first harness can be basic, but it must exist. A concrete first implementation may persist each session under `artifacts/benchmarks/<session_id>/` with a manifest plus per-case snapshots of the copied fixture, final recommendation, summary markdown, and a stable output digest for comparison against the previous session.

## Ralph Loop Artifacts

The Ralph loop itself must store iteration artifacts under `artifacts/agent_runs/` with:

- prompt copy
- Codex output
- verification output
- metadata

These are implementation artifacts, not end-user artifacts, but they are required for operator audit.
