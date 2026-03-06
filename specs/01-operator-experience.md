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

