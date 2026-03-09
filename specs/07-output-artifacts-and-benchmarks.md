# Output Artifacts And Benchmarks

## Final Artifacts

A completed `argus run` must persist:

- the normalized problem spec
- the full node archive
- score vectors
- critiques
- learning notes
- per-run outcome feedback artifacts when experiment results are later ingested
- any imported reusable-learning context used to steer the run
- the final recommendation object
- a readable markdown summary for humans

When the research-oriented runtime is used, a completed run must also persist a
decision-artifact bundle. At minimum this should include structured and
human-readable forms of:

- the search-space frame
- the coverage ledger
- proposal briefs
- triage outcomes
- deep-dive artifacts for surviving families
- adversarial reviews
- the comparison matrix
- hybrid assessments
- the final decision document

The repository should also persist:

- a root-level reusable learning-memory ledger so future non-benchmark runs can reuse compressed patterns with provenance
- a root-level outcome-feedback ledger so shipped experiment results remain auditable and reusable across runs

## Final Recommendation Requirements

The final recommendation object must include:

- identifiers for the selected nodes
- a human-readable summary
- explicit next experiments
- explicit assumptions and reversal conditions

The richer final decision artifact should additionally preserve:

- the runner-up and the condition under which it would win
- the conservative choice
- the high-upside risky choice
- the top risks with mitigation plans
- the first implementation spike and kill criteria
- the explicit decision rule used to act under uncertainty

Research-mode runs should also persist dedicated markdown outputs authored by the
final decision stage itself rather than only a local summary template. At minimum
that authored set should include:

- a concise decision summary markdown artifact for the top-level report
- a fuller final decision memo markdown artifact grounded in the comparison,
  deep-dive, and adversarial evidence

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

The benchmark harness should compare runtime modes directly when multiple search
paths exist. In particular, the repository should support comparing:

- the compact adaptive runtime
- the simpler staged research pipeline
- the coverage-led research runtime

Benchmarks should not only detect output drift. They should also make it
possible to compare decision quality and actionability across runtime modes.

The benchmark evaluation regime should increasingly focus on questions such as:

- would a serious team act on this output?
- are the tradeoffs explicit and specific?
- is the first spike concrete and discriminating?
- are the risks and reversal conditions decision-grade rather than generic?

To keep comparisons stable, the harness may isolate or disable shared cross-run learning memory while still persisting each case's own run artifacts.

The first harness can be basic, but it must exist. A concrete first implementation may persist each session under `artifacts/benchmarks/<session_id>/` with a manifest plus per-case snapshots of the copied fixture, final recommendation, summary markdown, and a stable output digest for comparison against the previous session.

## Ralph Loop Artifacts

The Ralph loop itself must store iteration artifacts under `artifacts/agent_runs/` with:

- prompt copy
- Codex output
- verification output
- metadata

These are implementation artifacts, not end-user artifacts, but they are required for operator audit.
