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

