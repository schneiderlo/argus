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

Run the stored benchmark suite, or a single case:

```bash
uv run argus benchmark
uv run argus benchmark --case technical-architecture-local-first
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
- A provider-backed evaluator and semantic novelty layer now exist in `src/argus/eval/`; they use the audited provider interface to return structured score vectors and novelty judgments instead of relying on hand-written lexical heuristics.
- `argus run` now executes the first working Argus runtime: it frames the problem, generates and de-duplicates candidates, stress-tests and deepens survivors, compresses learnings, and writes a compiled recommendation package to `artifacts/runs/<run_id>/`.
- Benchmark fixtures now live under `benchmarks/cases/`, and `argus benchmark` executes them into replayable benchmark sessions under `artifacts/benchmarks/<session_id>/`.

The remaining work is provider-routing statistics, persisted cross-run learning compression, and pairwise ranking support.

Process guardrails:

- `./scripts/verify.sh` uses `uv run --python 3.12 ...` to avoid silently validating against the wrong interpreter.
- `uv.lock` is expected to stay committed and in sync with `pyproject.toml`; verification should fail rather than rewriting the lockfile during a normal loop iteration.
- Python cache directories and bytecode files are ignored so loop runs do not dirty the tree with generated junk.
- A successful iteration is expected to end in a clean, committed repository state.
- The main evaluator and novelty layer are provider-backed and semantic. Deterministic logic is acceptable only for safety rails, validation, and cheap prefilters.
