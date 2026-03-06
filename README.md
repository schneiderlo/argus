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

Current CLI behavior:

- `argus inspect` works today for persisted Ralph-loop artifact directories and metadata files.
- `argus run` and `argus benchmark` fail explicitly until the remaining fix-plan items are implemented.

The remaining work is the actual Argus runtime: typed domain models, filesystem-backed state, provider integration, evaluation, novelty filtering, search control flow, final compilation, and benchmarks.

Process guardrails:

- `./scripts/verify.sh` uses `uv run --python 3.12 ...` to avoid silently validating against the wrong interpreter.
- `uv.lock` is expected to stay committed and in sync with `pyproject.toml`; verification should fail rather than rewriting the lockfile during a normal loop iteration.
- Python cache directories and bytecode files are ignored so loop runs do not dirty the tree with generated junk.
- A successful iteration is expected to end in a clean, committed repository state.
