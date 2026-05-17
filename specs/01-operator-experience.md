# Operator Experience

## Goal

The operator workflow must be simple enough to run in a terminal and strong enough to guide repeated implementation and evaluation work.

## Primary Loop

The repository must support a Ralph-style loop where the operator launches one shell command and lets Codex iterate:

```bash
./scripts/ralph-loop.sh
```

Each iteration must:

1. invoke Codex non-interactively with the live `PROMPT.md`
2. preserve the iteration artifacts
3. run deterministic verification
4. surface verification output to the next iteration

## Control Surfaces

The operator must be able to steer the system by editing:

- `PROMPT.md` for high-level behavioral instructions
- `fix_plan.md` for priority management
- files under `specs/` for product and technical truth

The operator should not need to edit the loop runner for normal steering.

The operator must also be able to feed back shipped experiment results without hand-editing stored ledgers. The repository should therefore expose a CLI workflow such as `argus feedback ...` that records typed outcome evidence against a persisted run/node and folds the derived learnings back into reusable memory.

## Toolchain Experience

The repo-facing workflow should stay stable whether the operator installs tools
directly on the host or enters an optional Nix dev shell on Linux/WSL. The
operator commands should still be the same repository commands:

- `uv sync --group dev`
- `uv run argus ...`
- `./scripts/verify.sh`

Nix may provision `python3.12`, `uv`, `node`, and `npm`, but it should not
replace `uv` as the package manager or the main command runner inside the
repository.

## Required Artifacts Per Iteration

Each run iteration must produce a dedicated folder under `artifacts/agent_runs/` that stores:

- the prompt used for the iteration
- the Codex output stream or JSONL event log
- the final assistant message
- the verification log
- a lightweight metadata file with timestamps and exit codes

## Failure Experience

When the repository is incomplete, the loop must fail loudly and usefully. Silent success is unacceptable. A failure should explain what is missing so the next Codex iteration can act on it.

## Stop Condition

The default operator experience should stop automatically when:

- `./scripts/verify.sh` exits with success
- and `fix_plan.md` has no remaining unchecked items

The operator must also be able to limit the number of iterations with an environment variable.

## Repo Ergonomics

The operator should be able to inspect the repository and understand:

- what Argus is supposed to do
- what remains missing
- what the last verification failure was
- what the last few loop iterations attempted

That means the docs, fix plan, and artifact layout must remain readable and current.

## Research Artifact Explorer

Research-mode runs should be inspectable through a file-explorer style tree in
the observer report. The tree should organize by durable decision artifacts
rather than by runtime nodes first:

- search frame and coverage ledger
- proposal families, with child items for brief, deep dive, technical dossier,
  and red-team review
- comparison matrices and hybrid assessments
- final decision summary, final memo, and typed decision object
- runtime evidence such as scheduler decisions

Selecting a tree item should keep the operator in the report and open a details
pane for that artifact. The details pane should render structured fields for
typed objects and markdown for authored memo or technical-dossier artifacts.
The node DAG remains useful as execution/debug evidence, but the primary
research report should be artifact-first so an operator can see what work
exists before reading it.
