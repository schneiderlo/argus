# Output Artifacts And Benchmarks

## Final Artifacts

A completed `argus run` must persist:

- the normalized problem spec
- the full node archive
- score vectors
- critiques
- learning notes
- the final recommendation object
- a readable markdown summary for humans

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

The first harness can be basic, but it must exist.

## Ralph Loop Artifacts

The Ralph loop itself must store iteration artifacts under `artifacts/agent_runs/` with:

- prompt copy
- Codex output
- verification output
- metadata

These are implementation artifacts, not end-user artifacts, but they are required for operator audit.

