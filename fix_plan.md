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

- [x] Implement bounded concurrent provider dispatch for independent search phases so `argus run` latency does not scale linearly with every evaluation, novelty, stress-test, and deepen call. Keep state commits deterministic, cap concurrency per provider, and prevent intra-batch novelty races.
- [x] Replace the thin generic evaluator and novelty prompts with action-specific judge prompts that encode the real rubric, hard-constraint handling, adversarial checks, duplicate criteria, and output expectations directly in the provider prompt materialized for Codex.
- [x] Add evaluator-quality benchmark fixtures and tests that catch obvious ranking, hard-constraint, pairwise-comparison, and novelty failures instead of only checking schema/plumbing behavior.
- [x] Bootstrap the Python project with `uv`: create `pyproject.toml`, `src/`, `tests/`, and an installable `argus` CLI entrypoint.
- [x] Implement the core typed domain models described in `specs/03-search-runtime.md` and `specs/04-evaluator-and-ranking.md`.
- [x] Implement a filesystem-backed state store for runs, nodes, learnings, scores, critiques, and final recommendations.
- [x] Implement a Codex provider adapter that wraps `codex exec`, validates structured outputs, captures logs, and never lets the provider write directly to repository state outside the orchestrated workflow.
- [x] Implement the provider-backed evaluator and semantic novelty judge.
- [x] Implement the first working search loop with these actions: `frame_problem`, `generate_seed`, `migrate`, `mutate`, `combine`, `stress_test`, `deepen`, `rank`, and `compress_learning`.
- [x] Implement final answer compilation with `best_bet`, `conservative_option`, `high_upside_option`, `rejected_but_insightful`, and `next_experiments`.
- [x] Add tests covering the CLI, provider contract, state store, evaluator, novelty filter, and search control flow.

## Next Priority

- [x] Replace the fixed mid-run phase chain with an adaptive frontier loop that decides whether to widen, stress-test, deepen, mutate, combine, or compress learning based on frontier width, critique coverage, and remaining budget.
- [x] Turn provider-routing statistics into a real action router so multi-provider runs can choose among a configured provider pool instead of collecting routing telemetry only.
- [x] Create benchmark fixtures for at least five representative problem types: product strategy, growth, UX, technical architecture, and monetization.
- [x] Add a benchmark harness that can run Argus against stored prompts and record structured outputs.
- [x] Add provider-routing statistics so the system can learn which provider performs best for each action.
- [x] Add pairwise ranking support to complement the provider-backed score vectors.

## Later

- [x] **Phase 1: Setup Svelte 5 & API Expansion**
  - [x] Initialize Svelte 5 + Vite under `src/argus/render/ui`.
  - [x] Expand `observe.py` with standard REST endpoints: `/api/runs`, `/api/runs/{id}/state`, `/api/memory`.
  - [x] Update the Python server to serve the Svelte `dist` folder.
- [x] **Phase 2: Parity with `observer.html`**
  - [x] Implement Svelte Flow (or Vis-Network wrapped in Svelte) for the node tree.
  - [x] Implement the Sidebar with reactive state for pruning.
- [x] **Phase 3: The New Views**
  - [x] Add SvelteKit routing for the Home Dashboard, Final Recommendation Report, and Learning Memory Ledger.

- [x] Add Gemini CLI and OpenCode provider adapters behind the same interface, while keeping Codex as the default and best-supported provider.
- [x] Add multi-island search so different optimization priors can evolve semi-independently.
- [x] Add outcome-feedback ingestion so shipped experiment results can influence future evaluation.
- [x] Add learning compression persistence so reusable patterns survive across runs.

## Notes

- Do not delete this file when work is complete. Turn it into a maintained project plan.
- If you discover a mismatch between the specs and implementation reality, record it here and then resolve it explicitly.
- The repository now includes typed domain models with explicit validation and deterministic JSON serialization in `src/argus/models/`.
- The filesystem-backed state store now lives in `src/argus/storage/state_store.py` and persists runs under `artifacts/runs/<run_id>/` with split JSON artifacts for nodes, scores, critiques, learning notes, and final recommendations.
- The Codex provider adapter now lives in `src/argus/providers/` and runs `codex exec` against an isolated read-only workspace while materializing prompt, schema, stdout, stderr, metadata, and failure artifacts under `artifacts/provider_invocations/` when wired into the runtime.
- `argus inspect` recognizes persisted Argus run directories as well as Ralph-loop artifact directories.
- The evaluator and novelty layer in `src/argus/eval/` now use provider-backed structured judgment rather than lexical heuristics.
- The evaluator/provider wiring now materializes action-specific judge prompts for evaluation, novelty, and pairwise ranking, and evaluator-quality benchmark assertions now exist in the repo. The next runtime priority is latency reduction through safe bounded concurrent dispatch.
- Evaluator-quality benchmark fixtures now live under `benchmarks/evaluator_cases/`, with typed loaders in `src/argus/benchmarks/evaluator_dataset.py` and data-driven tests in `tests/test_evaluator_benchmarks.py` covering hard-constraint failures, semantic novelty duplicates vs distinct shared-vocabulary ideas, pairwise objective-specific winner flips, and score-based finalist ordering.
- Codex prompt materialization now lives in `src/argus/providers/prompting.py` and gives `evaluate_candidate`, `assess_novelty`, and pairwise `rank` dedicated instructions covering authoritative evidence, hard constraints, adversarial checks, duplicate criteria, objective-specific ranking tradeoffs, and output expectations.
- The search runtime now dispatches bounded concurrent provider-backed work for archive novelty checks, candidate evaluation, stress tests, deepens, and mutations while preserving deterministic commit order at the state boundary. The runtime caps concurrent provider work via `SearchPolicy.provider_max_concurrency`, serializes final same-batch novelty admission, and keeps node ids and persisted artifacts stable even when provider calls finish out of order.
- The first working search runtime now lives in `src/argus/search/`; `argus run` frames the problem, seeds the archive, and then runs an adaptive frontier loop that reopens seed generation when width collapses, prioritizes early adversarial pressure, deepens or mutates promising survivors, opportunistically combines complementary nodes, periodically compresses learning, and persists a compiled final recommendation under `artifacts/runs/<run_id>/`.
- Benchmark fixtures now live under `benchmarks/cases/`, and `argus benchmark` records replayable benchmark sessions under `artifacts/benchmarks/<session_id>/` with per-case snapshots plus manifest-level output digests for change detection.
- Provider-routing summaries now persist per run at `artifacts/runs/<run_id>/routing-summary.json`, and the aggregate cross-run ledger now lives at `artifacts/runs/provider-routing-stats.json`.
- `argus run` and `argus benchmark` now accept a comma-separated provider pool. When more than one provider is configured, the runtime uses the persisted routing ledger to choose the best-scoring configured provider per routed action, while preserving the first provider as the deterministic fallback and recording both the actual source provider on each admitted node and the routed provider attributions for `assess_novelty` and `evaluate_candidate` so those judge actions can learn from downstream node outcomes too.
- The evaluator now supports provider-backed pairwise `rank` comparisons, and the runtime uses them to refine best-bet, conservative, and high-upside selection from the archived finalists instead of relying only on deterministic score ordering.
- Cross-run learning memory now persists at `artifacts/runs/learning-memory.json`, each run snapshots its imported subset at `artifacts/runs/<run_id>/reusable-learning-context.json`, and the runtime feeds those priors into framing, generation, evaluation, stress testing, deepening, mutation, combination, ranking, and learning compression. The benchmark harness keeps shared learning memory disabled so stored case outputs remain comparable across sessions.
- The provider layer now supports `codex`, `gemini`, and `opencode` behind the same typed contract. Codex remains the default and the most strongly supported path, while Gemini and OpenCode use their headless JSON surfaces plus the same audited prompt, artifact, and schema-validation pipeline.
- Concurrent CLI provider invocations now allocate artifact directories atomically in `src/argus/providers/cli_base.py`, so parallel `run_action` calls keep isolated prompt/schema/log artifacts instead of racing on shared invocation ids.
- `SearchPolicy.island_policies` now enables deterministic multi-island search. Each island persists its own archive/frontier/pruned bookkeeping through `SearchState.islands`, provider actions receive explicit island context, and the final recommendation summary labels which island produced each surviving bet while global novelty admission still prevents cross-island duplicates from racing into state.
- `argus feedback` now ingests shipped experiment outcomes against persisted run/node ids, writes per-run and aggregate outcome-feedback ledgers, merges outcome-backed learning notes into `artifacts/runs/learning-memory.json`, and updates the run-level plus aggregate provider-routing ledgers for the feedback node so future provider selection can learn from shipped outcomes rather than only from search-time proxy rewards.
- The adaptive frontier loop now includes explicit archive parent sampling, provider-mediated island migration, revisit beyond the live frontier, outcome-backed provider-routing updates, and a bounded finalist tournament instead of a top-two shortcut.
- `argus status` now reports the latest or selected run's persisted progress plus recent and active provider invocations, so the operator can see what stage is running without manually spelunking artifact directories.
- Final answer compilation now runs a bounded provider-backed pairwise tournament over a small finalist pool for `best_bet`, `conservative_option`, and `high_upside_option`, so a third- or fourth-ranked archived node can still win on direct head-to-head merit instead of being eliminated by a top-two pre-rank shortcut.
- `argus run` and `argus benchmark` now load optional TOML run-config files via `--run-config`, applying `provider_pool` and per-provider model overrides from `RunConfig` while still letting explicit `--provider` override the configured pool for that invocation.
- `argus run` now also supports `--prompt-file <path>` so multi-line requests can be supplied from disk instead of a single quoted positional argument, with explicit validation for missing/empty/conflicting request inputs.
- `argus dry-run` now validates request inputs (`--prompt-file` or inline), run-config/provider resolution, and local provider binary availability without executing provider actions, so operators can catch setup errors before spending provider calls.
- `argus observe` now annotates terminal nodes with a derived `termination_reason` (novelty rejection summary, hard-constraint failure reasons, or manual prune reason), and the observer sidebar renders that reason in a dedicated "Decision Reason" section so rejected branches are auditable at a glance.
- The main remaining paper-aligned gap is deeper future policy learning beyond provider routing, especially stronger outcome-backed search-control updates and benchmark regimes that measure decision quality rather than only replayable runtime behavior.
