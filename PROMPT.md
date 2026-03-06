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
8. Use `uv` for Python commands and tooling. The repository targets Python 3.12, not the host interpreter by default.
9. If verification passes, stage and commit the completed increment with a meaningful commit message so the repository does not remain green-but-dirty.
10. If you change Python dependencies or project metadata, update `uv.lock` in the same increment.
11. If verification still fails, use that output to drive the next increment and document the remaining gap in `fix_plan.md`.
12. If you change the operator workflow, update `README.md`, `AGENTS.md`, and this prompt if needed.
13. Do not use cheap keyword or lexical heuristics as the primary evaluator or novelty layer. Use provider-backed structured judgment, and keep deterministic logic limited to guardrails and validation.
14. Do not treat evaluator quality as complete just because provider plumbing exists. If the Codex-facing judge prompt for evaluation, novelty, or pairwise ranking is still generic or under-specified, harden that before adding more search sophistication.
15. For evaluation actions, prefer action-specific prompts over one generic wrapper. The prompt should explicitly encode the rubric, hard constraints, adversarial checks, duplicate criteria, and what evidence the judge must rely on.
16. Add benchmark-style tests that can fail when the evaluator makes bad decisions, not only when schemas or wiring break.

Product target:

- Build Argus as a Codex-first decision-and-invention engine.
- Treat idea generation as search over structured candidate states, not as a one-shot answer.
- Preserve archived stepping stones and reject near-duplicates.
- Use evaluator-first logic, not style-first logic.
- Prefer provider-backed semantic judgment over hand-written lexical scoring.
- Treat evaluator prompt quality and benchmarked judgment quality as first-class product work, not prompt polish.
- Produce final outputs that include a best bet, a conservative bet, a high-upside bet, rejected alternatives worth noting, and next experiments.

Quality bar:

- Strong typing
- Deterministic file-backed state
- Real schemas and structured data
- Real tests
- No silent failure paths
- No archive-conversation dependency
