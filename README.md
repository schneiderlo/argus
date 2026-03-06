# Argus Ralph Loop

This repository contains a Codex-first Ralph loop for building **Argus**, a decision-and-invention engine. The goal is not to preserve the archived conversation as context. The goal is to let a fresh agent implement the system from the repository itself.

The repository therefore includes:

- a self-contained specification library under `specs/`
- a repo-local `AGENTS.md` with implementation rules
- a live `PROMPT.md` that drives the Codex loop
- a prioritized `fix_plan.md`
- shell scripts for running the loop and deterministic verification
- JSON schemas for the core structured artifacts the system must eventually emit
- a Python package scaffold under `src/argus/` with an installable `argus` CLI

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

Run a single Argus search:

```bash
uv run argus run "Find the best retention strategy for a workflow-heavy product."
```

Run the same search through a non-default provider:

```bash
uv run argus run --provider gemini "Find the best retention strategy for a workflow-heavy product."
uv run argus run --provider opencode "Find the best retention strategy for a workflow-heavy product."
```

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

Run one Ralph-loop iteration:

```bash
RALPH_MAX_ITERS=1 ./scripts/ralph-loop.sh
```

Run the deterministic verification gate directly:

```bash
./scripts/verify.sh
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

## Loop Shape

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
- A provider-backed evaluator and semantic novelty layer now exist in `src/argus/eval/`; they use the audited provider interface to return structured score vectors, semantic novelty judgments, and pairwise `rank` decisions instead of relying on hand-written lexical heuristics.
- `argus run` now executes the first working Argus runtime: it frames the problem, generates and de-duplicates candidates, stress-tests and deepens survivors, compresses learnings, and writes a compiled recommendation package to `artifacts/runs/<run_id>/`.
- The runtime now dispatches bounded concurrent provider-backed work for archive novelty checks, candidate evaluation, stress tests, deepens, and mutations. Commits remain deterministic, node ids stay stable, and final same-batch novelty admission is serialized so near-duplicates cannot race into the archive together.
- The search runtime now also supports configurable multi-island search through `SearchPolicy.island_policies`, with per-island archive/frontier/pruned state persisted in each run and final summaries that label which island produced each selected bet.
- Provider-routing summaries now persist per run at `artifacts/runs/<run_id>/routing-summary.json`, and the runtime maintains an aggregate cross-run ledger at `artifacts/runs/provider-routing-stats.json` so future routing can learn from admitted nodes, strong scores, useful critiques, and winner contributions.
- Cross-run learning memory now persists at `artifacts/runs/learning-memory.json`, and each `argus run` snapshots the imported reusable subset it used at `artifacts/runs/<run_id>/reusable-learning-context.json` before feeding those priors back into later framing, generation, evaluation, ranking, and critique steps.
- `argus feedback` now records typed shipped-outcome evidence per run node, persists per-run and aggregate feedback ledgers, and folds outcome-backed learnings into the shared reusable-memory ledger so future evaluation can weight shipped evidence above search-only priors.
- Benchmark fixtures now live under `benchmarks/cases/`, and `argus benchmark` executes them into replayable benchmark sessions under `artifacts/benchmarks/<session_id>/`.

Benchmarks intentionally keep shared learning memory disabled so stored output digests stay comparable across sessions.

Process guardrails:

- `./scripts/verify.sh` uses `uv run --python 3.12 ...` to avoid silently validating against the wrong interpreter.
- `uv.lock` is expected to stay committed and in sync with `pyproject.toml`; verification should fail rather than rewriting the lockfile during a normal loop iteration.
- Python cache directories and bytecode files are ignored so loop runs do not dirty the tree with generated junk.
- A successful iteration is expected to end in a clean, committed repository state.
- The main evaluator and novelty layer are provider-backed and semantic. Deterministic logic is acceptable only for safety rails, validation, and cheap prefilters.
