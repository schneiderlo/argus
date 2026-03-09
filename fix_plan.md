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

- [x] Add first-class typed research-artifact models for `SearchSpaceFrame`, `SearchAxis`, `SearchCell`, `CoverageLedger`, `ProposalBrief`, `TriageReport`, `DeepDiveDoc`, `AdversarialReview`, `ComparisonMatrix`, `HybridAssessment`, and `FinalDecisionDoc` so Argus can persist decision-grade work instead of compressing everything back into `Candidate`.
- [x] Add a coverage-led research runtime alongside the current adaptive node runtime. The new runtime should explicitly frame the search space, maintain a coverage ledger of important cells or candidate families, seed representatives for uncovered cells, triage at the family level, deepen incumbents, red-team fragile survivors, gate hybrids with seam hypotheses, and write a final decision package from the full artifact set.
- [x] Add structured schemas and provider actions for the research pipeline stages: `frame_search_space`, `seed_cell_proposals`, `triage_proposals`, `deepen_family`, `redteam_family`, `assess_hybrid`, and `write_final_decision`.
- [x] Extend the filesystem state store so each run can persist a structured research-artifact bundle plus rendered markdown artifacts under the run directory, instead of relying on `_render_summary_markdown` as the main user-facing output path.
- [x] Add a new CLI/runtime mode for the research pipeline, keeping the current `argus run` path available as a control until the richer path wins on benchmarks.
- [x] Add benchmark support to compare three modes directly: the current adaptive runtime, the simple staged 5-step pipeline, and the new coverage-led research runtime. Use those results to decide when the richer path should become the default.

- [x] Implement bounded concurrent provider dispatch for independent search phases so `argus run` latency does not scale linearly with every evaluation, novelty, stress-test, and deepen call. Keep state commits deterministic, cap concurrency per provider, and prevent intra-batch novelty races.
- [x] Batch provider-backed novelty and evaluation for candidate-admission batches so multi-candidate generate/mutate/combine stages do not pay one semantic judge call per candidate while preserving structured judgments and serial same-batch dedupe.
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

- [x] Make the scheduler coverage-aware rather than quota-aware by introducing a coverage ledger with explicit cell/family status, uncertainty, hard-gate risk, evidence strength, and incumbent references. The scheduler now persists typed scheduler decisions and picks `expand`, `deepen`, `red-team`, `hybridize`, or `stop` from ledger state instead of fixed survivor quotas.
- [x] Add a provider-backed benchmark comparison judge so multi-mode benchmark sessions can score decision quality and actionability directly instead of relying only on side-by-side artifact review.
- [x] Replace generic node combination with a gated hybrid action that must name the repaired failure mode, complementary strengths, seam hypothesis, and complexity tax before a hybrid can survive.
- [x] Replace the current summary-template finish with a dedicated decision-authoring stage that reads the full artifact set and emits a typed final decision document plus richer markdown outputs.
- [x] Extend the observer/report views to surface research artifacts directly instead of only the node graph and summary markdown.
- [x] Unify the default runtime behavior so raw `SearchRuntime(policy=None)` and CLI defaults do not disagree about single-island versus portfolio search.

- [x] Replace the fixed mid-run phase chain with an adaptive frontier loop that decides whether to widen, stress-test, deepen, mutate, combine, or compress learning based on frontier width, critique coverage, and remaining budget.
- [x] Turn provider-routing statistics into a real action router so multi-provider runs can choose among a configured provider pool instead of collecting routing telemetry only.
- [x] Create benchmark fixtures for at least five representative problem types: product strategy, growth, UX, technical architecture, and monetization.
- [x] Add a benchmark harness that can run Argus against stored prompts and record structured outputs.
- [x] Add provider-routing statistics so the system can learn which provider performs best for each action.
- [x] Add pairwise ranking support to complement the provider-backed score vectors.

## Later

- [x] Move the observer UI off full-state polling onto typed status/event updates with periodic snapshot reconciliation, and expose a lightweight run-status API so the graph/report views can show current action, active invocations, and live event history without reloading the full search state every second.
- [x] Persist structured pairwise decision artifacts and surface them directly in the report view instead of relying on summary markdown alone.
- [ ] Upgrade the observer graph from action/id labels to idea-first labels plus island, migration, novelty, and winner-lineage overlays.
- [ ] Replace the memory ledger's provider-only aggregation with a provider x action matrix and reusable-learning filters that distinguish outcome-backed priors from search-only priors.

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
- [x] Align the observer Svelte memory and report views with the typed observer payloads so the UI reads `routing_stats.entries`, reusable learning provenance, `winner_ids`, and persisted `final_recommendation` artifacts instead of stale legacy field names.
- [x] Make `argus run --observe` keep the observer server alive after the search completes instead of dropping the daemon thread when the CLI exits.
- [x] Extend `RunConfig` so common execution defaults such as `cost_profile`, `progress`, `observe`, and `observe_port` can live in the TOML file instead of only on the command line.
- [x] Extend `RunConfig` so request input can also live in TOML via `request` or `prompt_file`, with CLI request flags taking precedence and prompt-file paths resolving relative to the config file.

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
- Codex prompt materialization in `src/argus/providers/prompting.py` now also gives `frame_problem`, `generate_seed`, `stress_test`, `deepen`, `mutate`, `combine`, and `compress_learning` dedicated instructions, hoisting search-policy guidance out of raw JSON payloads and into explicit action prompts instead of relying on the generic fallback prompt for core generation and critique behavior.
- Adaptive `combine` now runs through a typed hybrid gate in `src/argus/search/contracts.py` and `src/argus/search/runtime.py`: each proposed hybrid must carry a repaired failure mode, complementary strengths, seam hypothesis, explicit complexity tax, and a pursue/hold/reject verdict before any combined candidate can be admitted to the archive.
- The search runtime now dispatches bounded concurrent provider-backed work for archive novelty checks, candidate evaluation, stress tests, deepens, and mutations while preserving deterministic commit order at the state boundary. The runtime caps concurrent provider work via `SearchPolicy.provider_max_concurrency`, serializes final same-batch novelty admission, and keeps node ids and persisted artifacts stable even when provider calls finish out of order.
- The default `standard` cost profile now allows up to 8 concurrent provider tasks, and `max` allows up to 4, keeping high-exploration runs below the fan-out level that has recently destabilized provider latency.
- The first working search runtime now lives in `src/argus/search/`; `argus run` frames the problem, seeds the archive, and then runs an adaptive frontier loop that reopens seed generation when width collapses, prioritizes early adversarial pressure, deepens or mutates promising survivors, opportunistically combines complementary nodes, periodically compresses learning, and persists a compiled final recommendation under `artifacts/runs/<run_id>/`.
- Benchmark fixtures now live under `benchmarks/cases/`, and `argus benchmark` records replayable benchmark sessions under `artifacts/benchmarks/<session_id>/` with per-case snapshots plus manifest-level output digests for change detection.
- Provider-routing summaries now persist per run at `artifacts/runs/<run_id>/routing-summary.json`, and the aggregate cross-run ledger now lives at `artifacts/runs/provider-routing-stats.json`.
- `argus run` and `argus benchmark` now accept a comma-separated provider pool. When more than one provider is configured, the runtime uses the persisted routing ledger to choose providers per routed action with a deterministic UCB-style score over historical average reward plus an exploration bonus, while preserving the first provider as the fallback when an action has no prior signal and recording both the actual source provider on each admitted node and the routed provider attributions for `assess_novelty` and `evaluate_candidate` so those judge actions can learn from downstream node outcomes too.
- The evaluator now supports provider-backed pairwise `rank` comparisons, and the runtime uses them to refine best-bet, conservative, and high-upside selection from the archived finalists instead of relying only on deterministic score ordering.
- Cross-run learning memory now persists at `artifacts/runs/learning-memory.json`, each run snapshots its imported subset at `artifacts/runs/<run_id>/reusable-learning-context.json`, and the runtime feeds those priors into framing, generation, evaluation, stress testing, deepening, mutation, combination, ranking, and learning compression. The benchmark harness keeps shared learning memory disabled so stored case outputs remain comparable across sessions.
- The provider layer now supports `codex`, `gemini`, and `opencode` behind the same typed contract. Codex remains the default and the most strongly supported path, while Gemini and OpenCode use their headless JSON surfaces plus the same audited prompt, artifact, and schema-validation pipeline.
- The provider layer now strips accidental top-level JSON-schema metadata keys (for example `additionalProperties`) before typed validation when a model echoes schema keywords alongside an otherwise valid payload, while still rejecting genuinely unexpected business fields.
- Concurrent CLI provider invocations now allocate artifact directories atomically in `src/argus/providers/cli_base.py`, so parallel `run_action` calls keep isolated prompt/schema/log artifacts instead of racing on shared invocation ids.
- `SearchPolicy.island_policies` now enables deterministic multi-island search. Each island persists its own archive/frontier/pruned bookkeeping through `SearchState.islands`, provider actions receive explicit island context, and the final recommendation summary labels which island produced each surviving bet while global novelty admission still prevents cross-island duplicates from racing into state.
- `argus feedback` now ingests shipped experiment outcomes against persisted run/node ids, writes per-run and aggregate outcome-feedback ledgers, merges outcome-backed learning notes into `artifacts/runs/learning-memory.json`, and updates the run-level plus aggregate provider-routing ledgers for the feedback node so future provider selection can learn from shipped outcomes rather than only from search-time proxy rewards.
- The adaptive frontier loop now includes explicit archive parent sampling, provider-mediated island migration, revisit beyond the live frontier, outcome-backed provider-routing updates, and a bounded finalist tournament instead of a top-two shortcut.
- `argus status` now reports the latest or selected run's persisted progress plus recent and active provider invocations, so the operator can see what stage is running without manually spelunking artifact directories.
- Final answer compilation now runs a bounded provider-backed pairwise tournament over a small finalist pool for `best_bet`, `conservative_option`, and `high_upside_option`, so a third- or fourth-ranked archived node can still win on direct head-to-head merit instead of being eliminated by a top-two pre-rank shortcut.
- Adaptive runs now persist structured `pairwise_decisions` inside `final-recommendation.json`, validate those node references during snapshot load/save, and the observer report renders the grouped head-to-head tournament evidence directly instead of relying on summary markdown alone.
- `argus run` and `argus benchmark` now load optional TOML run-config files via `--run-config`, applying `provider_pool` and per-provider model overrides from `RunConfig` while still letting explicit `--provider` override the configured pool for that invocation.
- Run-config files now also support optional `budget` plus logical provider aliases via `[providers.<alias>] type = "codex|gemini|opencode"`, so the same backend can be routed as multiple distinct model-backed workers with separate routing attribution.
- Run-config files now also support common execution defaults such as `cost_profile`, `progress`, `verbose`, `observe`, and `observe_port`, with explicit CLI flags taking precedence for one-off overrides.
- Run-config files and CLI commands now also support a user-facing `search_profile` (`balanced` or `portfolio`) instead of making operators think in terms of raw `island_policies`. When omitted, `lean` defaults to `balanced`, while `standard` and `max` default to `portfolio`.
- Raw `SearchRuntime(policy=None)` now uses the same default adaptive policy as the CLI (`standard` cost profile, `portfolio` search profile) so programmatic runs and operator-facing runs agree on island shape unless the caller passes an explicit policy.
- Run-config files now also support request input via `request` or `prompt_file`, so `argus run` and `argus dry-run` can operate without a positional request when the TOML already defines one. `prompt_file` is resolved relative to the run-config file, and CLI request inputs still take precedence.
- `argus run` now also supports `--prompt-file <path>` so multi-line requests can be supplied from disk instead of a single quoted positional argument, with explicit validation for missing/empty/conflicting request inputs.
- `argus dry-run` now validates request inputs (`--prompt-file` or inline), run-config/provider resolution, and local provider binary availability without executing provider actions, so operators can catch setup errors before spending provider calls.
- `argus run`, `argus dry-run`, and `argus benchmark` now accept `--cost-profile lean|standard|max`, mapping common operator intent onto concrete `SearchPolicy` presets instead of forcing manual policy tuning for low-cost versus high-exploration runs.
- `argus observe` now annotates terminal nodes with a derived `termination_reason` (novelty rejection summary, hard-constraint failure reasons, or manual prune reason), and the observer sidebar renders that reason in a dedicated "Decision Reason" section so rejected branches are auditable at a glance.
- `argus run --observe` now starts the observer during the run and then keeps the server alive after the final recommendation is printed, so operators can leave the browser open on the just-finished run without launching a separate `argus observe` process.
- Multi-provider routed actions now retry against the remaining configured providers when the first choice fails or times out, while still recording provider-failure counts for the failed attempts in routing telemetry and keeping admitted-node attribution tied to the provider that ultimately succeeded.
- `./scripts/verify.sh` now gates observer UI changes with both `npm --prefix src/argus/render/ui run check` and `npm --prefix src/argus/render/ui run build`, so the served `src/argus/render/dist` bundle cannot silently drift behind the Svelte source tree.
- The observer now exposes `/api/runs/{id}/status` plus `/api/status`, the Svelte UI consumes typed API contracts instead of `any`, the run graph polls status/events with periodic snapshot reconciliation, the report auto-refreshes while a run is active, and the dashboard/top bar now show search-budget terminology plus live current-action context.
- The main remaining paper-aligned gap is deeper future policy learning beyond provider routing, especially stronger outcome-backed search-control updates and benchmark regimes that measure decision quality rather than only replayable runtime behavior.
- The research final-decision stage now returns provider-authored `decision_summary_markdown` and `decision_report_markdown` alongside the typed comparison matrix and `FinalDecisionDoc`, so the operator-facing report is grounded in the full artifact bundle instead of a local summary template.
- `argus run --runtime-mode research` now executes a staged coverage-led pipeline (`frame_search_space`, `seed_cell_proposals`, `triage_proposals`, `deepen_family`, `redteam_family`, optional `assess_hybrid`, then `write_final_decision`) while `--runtime-mode adaptive` keeps the existing search loop as the control path.
- Research-mode runs now persist `research/bundle.json` plus rendered markdown artifacts under `research/markdown/` inside each run directory, and `load_run()` exposes the typed `research_bundle` alongside the existing search-state and final-recommendation payloads.
- `argus benchmark` now compares `adaptive`, `staged`, and `research` per case by default, persisting mode-specific outputs under `artifacts/benchmarks/<session_id>/cases/<case_id>/<runtime_mode>/` and tracking digest drift separately for each mode across sessions.
- Benchmark sessions now also persist a provider-backed per-case comparison artifact (`comparison.json` plus `comparison.md`) that scores decision quality, actionability, tradeoff clarity, risk quality, and experiment quality across runtime modes, marks a winner and runner-up, and records skipped/failed comparison states in the session manifest.
- The observer state payload now includes the persisted `research_bundle`, and the final report renders typed research artifacts directly: search-space framing, coverage ledger cells, proposal briefs, triage and scheduler traces, deep dives, adversarial reviews, comparison matrices, hybrid assessments, and the final decision document/memo.
