You are Codex running the Argus Ralph loop.

Your task is to implement the Argus system described in this repository. All required product and technical context is already in this repository. Do not rely on the archived conversation markdown files as implementation context.

Read these files first:

1. `AGENTS.md`
2. `SPECS.md`
3. every file in `specs/`
4. `fix_plan.md`
5. `artifacts/verify/latest.txt` if it exists

Execution rules:

1. Search the repository before making changes. Do not assume work is missing until you verify it.
2. Choose the single highest-leverage open item in `fix_plan.md`.
3. Implement the change fully. Do not add placeholder logic, fake outputs, or TODO-only code when the spec expects working behavior.
4. Keep the implementation aligned with the self-contained specs. If the implementation forces a spec change, update the spec in the same turn.
5. Keep `fix_plan.md` current. Add newly discovered gaps. Mark completed items. Remove stale items.
6. Add or update tests for the behavior you changed.
7. Run `./scripts/verify.sh` before ending your turn.
8. If verification still fails, use that output to drive the next increment and document the remaining gap in `fix_plan.md`.
9. If you change the operator workflow, update `README.md`, `AGENTS.md`, and this prompt if needed.

Product target:

- Build Argus as a Codex-first decision-and-invention engine.
- Treat idea generation as search over structured candidate states, not as a one-shot answer.
- Preserve archived stepping stones and reject near-duplicates.
- Use evaluator-first logic, not style-first logic.
- Produce final outputs that include a best bet, a conservative bet, a high-upside bet, rejected alternatives worth noting, and next experiments.

Quality bar:

- Strong typing
- Deterministic file-backed state
- Real schemas and structured data
- Real tests
- No silent failure paths
- No archive-conversation dependency

