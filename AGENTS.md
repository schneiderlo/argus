# Argus Agent Rules

This file is the repo-local operating contract for Codex runs in this repository.

## Mission

Implement **Argus**, a Codex-first decision-and-invention engine that treats brainstorming as structured search over candidate solutions instead of as a single chat response.

## Source Of Truth

All required context is inside this repository. Do not depend on the archived conversation files for implementation context unless the operator explicitly asks for historical comparison.

Read in this order:

1. `AGENTS.md`
2. `SPECS.md`
3. every file in `specs/`
4. `fix_plan.md`
5. the latest verification log at `artifacts/verify/latest.txt` if it exists

## Working Rules

1. Before making changes, search the codebase. Do not assume a feature is missing until you verify it.
2. Work on the single highest-leverage item in `fix_plan.md` that moves the repository toward a working Argus implementation.
3. Keep `fix_plan.md` accurate. Add newly discovered gaps, mark completed work, and remove obsolete work.
4. Do not implement placeholder, fake, or toy logic when the specs call for real behavior.
5. Every meaningful behavior change must include tests or, if testing is blocked, a precise note in `fix_plan.md` explaining the missing coverage.
6. Run `./scripts/verify.sh` before ending your turn. Treat the output as hard backpressure.
7. When verification passes, leave the repository in a clean state. Stage and commit the completed increment with a meaningful commit message instead of leaving a green but dirty tree behind.
8. Keep docs in sync with reality. If the implementation changes the operator workflow or system architecture, update the relevant files in `specs/`, `README.md`, and `PROMPT.md`.
9. Favor a clean Python implementation with typed models and deterministic file-based state over cleverness.
10. If you change Python dependencies or project metadata, update `uv.lock` in the same increment and commit it.
11. Do not reintroduce cheap lexical heuristics as the main evaluator or novelty layer. Use provider-backed structured judgment; keep deterministic logic limited to guardrails and validation.

## Coding Direction

The target application described by the specs is a Python 3.12 project with:

- a CLI entrypoint named `argus`
- `uv` as the package manager and environment runner
- typed domain models for problem specs, candidates, critique objects, score vectors, nodes, learning notes, and final recommendations
- a local filesystem state store
- a provider abstraction with Codex as the first-class provider
- evaluator-first search with provider-backed semantic judgment, novelty filtering, and archived stepping stones
- outcome-feedback ingestion that folds shipped experiment results back into reusable learning memory with provenance

## Ralph Loop Behavior

The loop is intentionally simple:

- `PROMPT.md` is the live prompt Codex receives.
- `./scripts/ralph-loop.sh` repeatedly invokes `codex exec`.
- `./scripts/verify.sh` is the deterministic gate.

The operator will tune `PROMPT.md` and `fix_plan.md` over time. Respect both files as mutable control surfaces.

`./scripts/verify.sh` is expected to run through `uv` on Python 3.12. Passing verification with a dirty worktree is treated as process failure, not success.
