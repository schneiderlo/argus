# Argus Ralph Loop

This repository contains a Codex-first Ralph loop for building **Argus**, a decision-and-invention engine. The goal is not to preserve the archived conversation as context. The goal is to let a fresh agent implement the system from the repository itself.

The repository therefore includes:

- a self-contained specification library under `specs/`
- a repo-local `AGENTS.md` with implementation rules
- a live `PROMPT.md` that drives the Codex loop
- a prioritized `fix_plan.md`
- shell scripts for running the loop and deterministic verification
- JSON schemas for the core structured artifacts the system must eventually emit

## Quick Start

Run one iteration:

```bash
RALPH_MAX_ITERS=1 ./scripts/ralph-loop.sh
```

Run until verification passes and the open items in `fix_plan.md` are gone:

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
4. Copies the latest verification log to `artifacts/verify/latest.txt`.
5. Repeats until the operator stops it or the repository reaches a verified state.

## Current State

The repository intentionally starts as a spec-and-loop package, not as a finished application. `./scripts/verify.sh` currently fails until the Python application described in `specs/` is implemented. That failure is part of the loop: it tells Codex what remains missing.

When the Python project scaffold is created, use `uv` as the package manager and environment runner.
