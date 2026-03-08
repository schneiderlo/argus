# Argus

This repository contains **Argus**, a decision-and-invention engine that treats brainstorming as structured search instead of a single chat response.

The Ralph loop in this repo is a development workflow for iterating on the project with Codex. It is useful for building and maintaining Argus, but it is not the product itself and not the main runtime path for normal Argus use.

The goal is not to preserve the archived conversation as context. The goal is to let a fresh agent implement and operate the system from the repository itself.

The repository therefore includes:

- an installable `argus` CLI under `src/argus/`
- a self-contained specification library under `specs/`
- a repo-local `AGENTS.md` with implementation rules
- a live `PROMPT.md` that drives the optional Codex development loop
- a prioritized `fix_plan.md`
- shell scripts for deterministic verification and the optional Ralph loop
- JSON schemas for the core structured artifacts the system must eventually emit
- benchmark fixtures and persisted artifact directories

## Quick Start

Prepare the local Python environment:

```bash
uv sync --group dev
```

The repository targets Python 3.12 through `uv`. Do not rely on the system `python3` for normal development or verification.

Inspect the scaffolded CLI:

```bash
uv run argus --help
```

Check the latest run status:

```bash
uv run argus status
```

Run a single Argus search:

```bash
uv run argus run "Find the best retention strategy for a workflow-heavy product."
```

Run a search and keep the observer web UI open for that run:

```bash
uv run argus run --observe --observe-port 8080 \
  "Find the best retention strategy for a workflow-heavy product."
```

`--observe` starts the observer during the run and keeps it available afterward until you press
`Ctrl-C`. Use plain `uv run argus observe` when you want to inspect an existing run without
starting a new one.

Choose how aggressively Argus spends search effort:

```bash
uv run argus run --cost-profile lean "Find the best retention strategy for a workflow-heavy product."
uv run argus run --cost-profile max "Find the best retention strategy for a workflow-heavy product."
```

`lean` trims frontier width and branch work to reduce cost, `standard` keeps the default
policy, and `max` expands the search for broader exploration.

Run a search request from a file instead of inline text:

```bash
cat > request.txt <<'EOF'
Find the best retention strategy for a workflow-heavy product.
Focus on weekly workflow habits and explicit failure modes.
EOF

uv run argus run --prompt-file request.txt
```

Run the same search through a non-default provider:

```bash
uv run argus run --provider gemini "Find the best retention strategy for a workflow-heavy product."
uv run argus run --provider opencode "Find the best retention strategy for a workflow-heavy product."
```

Run the search through a provider pool so Argus can route each action using persisted
provider-routing stats with deterministic UCB-style exploration while falling back to the
first provider in the list when no action history exists:

```bash
uv run argus run --provider codex,gemini,opencode \
  "Find the best retention strategy for a workflow-heavy product."
```

Run through a TOML run-config that defines the provider pool plus common execution defaults such as budget, cost profile, and observer behavior:

```toml
# run-config.toml
budget = 12
cost_profile = "standard"
progress = "quiet"
observe = true
observe_port = 8080
# Optional: move the request into the config instead of the CLI.
# Set either `request` or `prompt_file`, not both.
# request = """Find the best retention strategy for a workflow-heavy product."""
# prompt_file = "request.txt"
provider_pool = ["codex", "gemini", "opencode"]

[providers.codex]
model = "gpt-5-codex"

[providers.gemini]
model = "gemini-2.5-pro"

[providers.opencode]
model = "o4-mini"
```

```bash
uv run argus run --run-config run-config.toml \
  "Find the best retention strategy for a workflow-heavy product."
uv run argus benchmark --run-config run-config.toml
```

`--provider`, `--budget`, `--cost-profile`, `--progress`, `--observe`, `--no-observe`, and `--observe-port` still work and override the corresponding run-config values for that command.

You can also let the run-config carry the request input:

```toml
request = """
Find the best retention strategy for a workflow-heavy product.
Focus on weekly workflow habits and explicit failure modes.
"""

provider_pool = ["codex"]

[providers.codex]
model = "gpt-5-codex"
```

```bash
uv run argus run --run-config run-config.toml
uv run argus dry-run --run-config run-config.toml
```

Or point the config at a request file relative to the config file itself:

```toml
prompt_file = "request.txt"
provider_pool = ["codex"]

[providers.codex]
model = "gpt-5-codex"
```

You can also define logical provider aliases so different models from the same backend are
routed and tracked independently:

```toml
budget = 12
provider_pool = ["codex_fast", "gemini_flash", "gemini_flash_lite"]

[providers.codex_fast]
type = "codex"
model = "gpt-5.3-codex-spark"

[providers.gemini_flash]
type = "gemini"
model = "gemini-3-flash-preview"

[providers.gemini_flash_lite]
type = "gemini"
model = "gemini-3.1-flash-lite-preview"
```

Validate prompt/config/provider setup before running a real search:

```bash
uv run argus dry-run --run-config run-config.toml --prompt-file request.txt
uv run argus dry-run "Find the best retention strategy." --provider codex --cost-profile lean --json
```

`argus dry-run` does not execute provider actions. It validates request input, run-config parsing,
provider resolution, and local provider binary availability.

Run-config rules:

- `budget` is optional and applies to `argus run` and `argus dry-run`.
- `request` and `prompt_file` are optional and apply to `argus run` and `argus dry-run`.
- Set only one of `request` or `prompt_file` in a run-config.
- `prompt_file` is resolved relative to the run-config file when it is not absolute.
- `cost_profile` is optional and applies to `argus run`, `argus dry-run`, and `argus benchmark`.
- `progress` is optional and applies to `argus run`.
- `verbose` is optional and applies to `argus run`.
- `observe` and `observe_port` are optional and apply to `argus run`.
- `provider_pool` is the ordered provider fallback/routing pool for the run.
- Every provider listed in `provider_pool` must have a matching `[providers.<name>]` table.
- `type` is optional when the provider table name is already `codex`, `gemini`, or `opencode`. Use `type` for aliases such as `codex_fast` or `gemini_flash_lite`.
- `model` is optional per provider; if omitted, the provider default/env behavior is used.
- If `--provider` is passed, that value is used instead of `provider_pool` from the file.
- If a positional request or `--prompt-file` is passed, that value is used instead of `request` or `prompt_file` from the file.
- If `--budget` is passed, that value is used instead of `budget` from the file.
- CLI flags win over run-config values when both are provided.

Run the stored benchmark suite, or a single case:

```bash
uv run argus benchmark
uv run argus benchmark --case technical-architecture-local-first
```

Record shipped outcome feedback against a persisted run/node and feed it back into reusable memory:

```bash
uv run argus feedback run-20260306T020456Z --node node-0007 --outcome validated \
  --summary "Teams kept returning because weekly review prep got faster." \
  --winning-pattern "Teams accept setup work when the audit trail saves recurring review time."
```

Run the deterministic verification gate directly:

```bash
./scripts/verify.sh
```

## Development Loop

The Ralph loop is a repo-maintenance path for using Codex to improve the project itself. It is not required for ordinary `argus run`, `argus benchmark`, or `argus feedback` usage.

Run one Ralph-loop iteration:

```bash
RALPH_MAX_ITERS=1 ./scripts/ralph-loop.sh
```

Run the Ralph loop until verification passes and the open items in `fix_plan.md` are gone:

```bash
./scripts/ralph-loop.sh
```

Optional environment variables:

- `CODEX_MODEL`: pass `-m` to `codex exec`
- `RALPH_MAX_ITERS`: stop after a fixed number of iterations; `0` means no limit
- `RALPH_SLEEP_SECONDS`: delay between iterations; default `2`
- `RALPH_STOP_ON_PASS`: `1` to stop when verification passes and `fix_plan.md` has no unchecked items
- `CODEX_JSON`: `1` to capture JSONL event output, `0` for plain text

## Ralph Loop Shape

Each iteration does the following:

1. Runs `codex exec` against `PROMPT.md`.
2. Stores the agent transcript artifacts under `artifacts/agent_runs/`.
3. Runs `./scripts/verify.sh` to generate deterministic backpressure.
4. Fails the iteration if verification passes but the repository is still dirty.
5. Copies the latest verification log to `artifacts/verify/latest.txt`.
6. Repeats until the operator stops it or the repository reaches a verified state.

## Current State

The repository now contains the Python project scaffold described in `specs/02-system-architecture.md`: `pyproject.toml`, `src/`, `tests/`, and an installable `argus` CLI entrypoint.

Current implementation status:

- `argus inspect` works today for persisted Ralph-loop artifact directories and for Argus run directories under `artifacts/runs/`.
- The core typed domain models now exist in `src/argus/models/` with explicit validation and deterministic `to_dict`/`from_dict` round-tripping.
- A filesystem-backed state store now exists in `src/argus/storage/` and persists problem specs, nodes, scores, critiques, learning notes, and final recommendations under `artifacts/runs/<run_id>/`.
- A production Codex provider adapter now exists in `src/argus/providers/`; it runs `codex exec` in an isolated read-only workspace, captures audited prompt/schema/log artifacts, and validates structured outputs before returning typed data to the runtime.
- The provider layer now also supports `gemini` and `opencode` behind the same typed contract and `--provider` CLI flag. Codex remains the default and the best-supported path; the additional adapters reuse the same audited prompt, artifact, and validation flow while speaking each CLI's native headless JSON surface.
- `argus run` and `argus benchmark` now also accept a comma-separated provider pool such as `--provider codex,gemini,opencode`. When a pool is present, Argus consults persisted provider-routing stats to choose which configured provider should handle each routed action, including `generate_seed`, `assess_novelty`, `evaluate_candidate`, and pairwise `rank`, using a deterministic UCB-style score over average historical reward plus an exploration bonus while still falling back to the first provider when the action has no prior signal yet.
- If a routed provider fails or times out during a multi-provider run, Argus retries the same action against the remaining configured providers in deterministic fallback order and still records the failed attempt in routing telemetry.
- `argus run`, `argus dry-run`, and `argus benchmark` now also accept `--cost-profile lean|standard|max`, which maps to concrete `SearchPolicy` presets so operators can trade search breadth against provider spend without manually editing runtime knobs.
- A provider-backed evaluator and semantic novelty layer now exist in `src/argus/eval/`; they use the audited provider interface to return structured score vectors, semantic novelty judgments, and pairwise `rank` decisions instead of relying on hand-written lexical heuristics.
- `argus run` now executes the first working Argus runtime: it frames the problem, seeds and de-duplicates candidates, then runs an adaptive frontier loop that can widen search again, stress-test promising branches early, deepen or mutate survivors, combine complementary nodes, migrate strong ideas into plateaued islands through provider-mediated rewrites, revisit archived stepping stones when stage capacity exceeds the current frontier, compress learnings, and write a compiled recommendation package to `artifacts/runs/<run_id>/`.
- Final answer compilation now uses a bounded pairwise tournament over the strongest archived finalists for `best_bet`, `conservative_option`, and `high_upside_option`, so a slightly lower pre-ranked candidate can still win by direct provider-judged head-to-head comparisons.
- The runtime now dispatches bounded concurrent provider-backed work for archive novelty checks, candidate evaluation, stress tests, deepens, and mutations. Commits remain deterministic, node ids stay stable, and final same-batch novelty admission is serialized so near-duplicates cannot race into the archive together.
- The search runtime now also supports configurable multi-island search through `SearchPolicy.island_policies`, with per-island archive/frontier/pruned state persisted in each run, conservative cross-island migration that adapts strong source-island candidates into plateaued destination islands without breaking same-island parent invariants, and final summaries that label which island produced or adopted each selected bet.
- Provider-routing summaries now persist per run at `artifacts/runs/<run_id>/routing-summary.json`, and the runtime maintains an aggregate cross-run ledger at `artifacts/runs/provider-routing-stats.json` so future routing can learn not just from source-generation actions but also from routed novelty checks, candidate scoring, useful critiques, and winner contributions.
- Cross-run learning memory now persists at `artifacts/runs/learning-memory.json`, and each `argus run` snapshots the imported reusable subset it used at `artifacts/runs/<run_id>/reusable-learning-context.json` before feeding those priors back into later framing, generation, evaluation, ranking, and critique steps.
- `argus feedback` now records typed shipped-outcome evidence per run node, persists per-run and aggregate feedback ledgers, folds outcome-backed learnings into the shared reusable-memory ledger, and updates the provider-routing ledgers for the feedback node so future action routing can learn from shipped outcomes instead of only search-time winners.
- Benchmark fixtures now live under `benchmarks/cases/`, and `argus benchmark` executes them into replayable benchmark sessions under `artifacts/benchmarks/<session_id>/`.

Benchmarks intentionally keep shared learning memory disabled so stored output digests stay comparable across sessions.

Process guardrails:

- `./scripts/verify.sh` uses `uv run --python 3.12 ...` to avoid silently validating against the wrong interpreter, and it also runs `npm --prefix src/argus/render/ui run check` plus `npm --prefix src/argus/render/ui run build` so observer UI type regressions and stale packaged bundles fail the Ralph loop.
- `uv.lock` is expected to stay committed and in sync with `pyproject.toml`; verification should fail rather than rewriting the lockfile during a normal loop iteration.
- Python cache directories and bytecode files are ignored so loop runs do not dirty the tree with generated junk.
- A successful iteration is expected to end in a clean, committed repository state.
- The main evaluator and novelty layer are provider-backed and semantic. Deterministic logic is acceptable only for safety rails, validation, and cheap prefilters.

# Current tests

uv run argus run --cost-profile max --run-config run-config.codex-gemini-trio.toml --prompt-file workspace.md
