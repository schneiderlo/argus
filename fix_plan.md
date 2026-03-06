# Argus Fix Plan

This file is the live prioritized work queue for the Argus implementation. Update it continuously as the repository evolves.

## Completion Definition

Argus is not done when it can print a plausible brainstorm. The initial target is complete only when the repository has:

- a real Python project scaffold
- a working `argus` CLI
- typed core domain models
- a persistent filesystem-backed search state store
- a Codex provider wrapper built on `codex exec`
- provider-backed evaluator and semantic novelty implementations
- a runnable search loop
- answer compilation logic
- tests for the critical path
- benchmark fixtures and a harness skeleton

## Highest Priority

- [x] Bootstrap the Python project with `uv`: create `pyproject.toml`, `src/`, `tests/`, and an installable `argus` CLI entrypoint.
- [x] Implement the core typed domain models described in `specs/03-search-runtime.md` and `specs/04-evaluator-and-ranking.md`.
- [x] Implement a filesystem-backed state store for runs, nodes, learnings, scores, critiques, and final recommendations.
- [x] Implement a Codex provider adapter that wraps `codex exec`, validates structured outputs, captures logs, and never lets the provider write directly to repository state outside the orchestrated workflow.
- [x] Implement the provider-backed evaluator and semantic novelty judge.
- [x] Implement the first working search loop with these actions: `frame_problem`, `generate_seed`, `mutate`, `combine`, `stress_test`, `deepen`, `rank`, and `compress_learning`.
- [x] Implement final answer compilation with `best_bet`, `conservative_option`, `high_upside_option`, `rejected_but_insightful`, and `next_experiments`.
- [x] Add tests covering the CLI, provider contract, state store, evaluator, novelty filter, and search control flow.

## Next Priority

- [x] Create benchmark fixtures for at least five representative problem types: product strategy, growth, UX, technical architecture, and monetization.
- [x] Add a benchmark harness that can run Argus against stored prompts and record structured outputs.
- [x] Add provider-routing statistics so the system can learn which provider performs best for each action.
- [x] Add pairwise ranking support to complement the provider-backed score vectors.

## Later

- [ ] Add Gemini CLI and OpenCode provider adapters behind the same interface, while keeping Codex as the default and best-supported provider.
- [ ] Add multi-island search so different optimization priors can evolve semi-independently.
- [ ] Add outcome-feedback ingestion so shipped experiment results can influence future evaluation.
- [ ] Add learning compression persistence so reusable patterns survive across runs.

## Notes

- Do not delete this file when work is complete. Turn it into a maintained project plan.
- If you discover a mismatch between the specs and implementation reality, record it here and then resolve it explicitly.
- The repository now includes typed domain models with explicit validation and deterministic JSON serialization in `src/argus/models/`.
- The filesystem-backed state store now lives in `src/argus/storage/state_store.py` and persists runs under `artifacts/runs/<run_id>/` with split JSON artifacts for nodes, scores, critiques, learning notes, and final recommendations.
- The Codex provider adapter now lives in `src/argus/providers/` and runs `codex exec` against an isolated read-only workspace while materializing prompt, schema, stdout, stderr, metadata, and failure artifacts under `artifacts/provider_invocations/` when wired into the runtime.
- `argus inspect` recognizes persisted Argus run directories as well as Ralph-loop artifact directories.
- The evaluator and novelty layer in `src/argus/eval/` now use provider-backed structured judgment rather than lexical heuristics.
- The first working search runtime now lives in `src/argus/search/`; `argus run` frames the problem, generates and filters seeds, stress-tests and deepens survivors, compresses learnings, and persists a compiled final recommendation under `artifacts/runs/<run_id>/`.
- Benchmark fixtures now live under `benchmarks/cases/`, and `argus benchmark` records replayable benchmark sessions under `artifacts/benchmarks/<session_id>/` with per-case snapshots plus manifest-level output digests for change detection.
- Provider-routing summaries now persist per run at `artifacts/runs/<run_id>/routing-summary.json`, and the aggregate cross-run ledger now lives at `artifacts/runs/provider-routing-stats.json`.
- The evaluator now supports provider-backed pairwise `rank` comparisons, and the runtime uses them to refine best-bet, conservative, and high-upside selection from the archived finalists instead of relying only on deterministic score ordering.
