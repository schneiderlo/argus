# Provider Integration

## Provider Philosophy

Providers are workers, not product brains. The orchestrator owns prompts, schemas, validation, persistence, and evaluation.

## Codex Is The Main Provider

The first implementation must use `codex exec` as the main provider path because it supports non-interactive execution and clean shell integration.

The intended invocation shape is:

```bash
codex exec --full-auto -C "$ROOT" - < prompt.md
```

The real wrapper should add:

- a model override when configured
- structured output capture
- prompt materialization for audit
- schema validation
- timeout and error handling

## Required Provider Contract

Every provider must implement one logical method:

- accept an action name
- accept a problem spec
- accept an input payload
- accept an output schema
- return structured data that matches schema

No provider may directly mutate repository state as part of its contract. Only the orchestrator may decide what becomes persisted state.

The orchestrator also owns the full action-specific prompt design. A provider adapter may materialize a generic wrapper, but Argus must supply rich per-action instructions for evaluation, novelty, pairwise ranking, generation, and critique behaviors rather than relying on the model to infer intent from raw JSON alone.

Provider implementations should also support a bounded-concurrency execution model so the runtime can dispatch independent work in parallel without building a separate orchestration path per provider. This can be implemented with async APIs, worker pools, or another explicit concurrency mechanism, but it must preserve the same artifact capture, schema validation, timeout handling, and failure serialization guarantees as the synchronous path.

When the operator configures more than one provider for a run, the orchestrator should treat that as a provider pool rather than as a fixed one-provider run. In that mode the orchestrator may choose the provider per action using persisted provider-routing statistics and action-level reward signals, while still keeping one explicit fallback provider for actions with no strong historical signal. This routing should apply not just to generation and critique actions, but also to provider-backed novelty checks, candidate evaluation, and pairwise ranking, with the runtime persisting enough attribution metadata to fold downstream node outcomes back into the routing ledger for those judge actions.

If a routed provider attempt fails, the orchestrator should retry the same action against the remaining configured providers in a deterministic order before failing the run. Provider-failure telemetry must still be recorded for the failed attempts.

## Initial Provider Scope

The first implementation only needs a production-quality Codex adapter. Gemini CLI and OpenCode can arrive later, but the interface must not make their addition awkward.

## Failure Handling

Provider failures must be explicit and serializable. The system must record:

- the provider name
- action name
- prompt path or prompt digest
- exit status
- stderr or equivalent failure detail
- timestamp

## Schema Requirement

Structured outputs are mandatory. The provider layer must not admit free-form prose into the runtime without parsing and validation.

## Prompt Audit Requirement

Provider invocation artifacts must make it easy to inspect the exact prompt that was sent for each action. This is especially important for evaluator, novelty, and pairwise ranking actions because prompt quality is part of the product, not incidental glue code.

## Concurrency Audit Requirement

If providers are dispatched concurrently, each invocation still needs isolated artifacts, explicit timing metadata, and unambiguous association back to the runtime action that triggered it. Parallelism must not make failures or prompt provenance harder to debug.
