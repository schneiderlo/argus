# Safety And Quality Bars

## Implementation Quality Bar

Argus must prefer explicit, testable engineering over vague agent theater.

The following are mandatory:

- typed models
- explicit persistence
- deterministic verification
- clear failures
- test coverage for the critical path
- doc updates when behavior changes

## Prohibited Shortcuts

The implementation must not rely on:

- placeholder logic presented as complete behavior
- silent error swallowing
- implicit global mutable state
- free-form unvalidated provider outputs
- dependence on archived conversation files as runtime context

## Testing Rules

Every critical subsystem needs tests:

- CLI behavior
- model serialization
- state store persistence and replay
- evaluator calculations
- novelty filter admission rules
- provider contract behavior
- search loop control flow
- final recommendation compilation

## Failure Handling

When a step fails, the system must preserve enough data to debug the failure. Failure should leave behind:

- error type
- error context
- location of relevant artifacts
- whether state is safe to resume

## Documentation Rule

If the implementation diverges from the current spec, update the spec in the same change or document the mismatch in `fix_plan.md`. Do not let docs drift silently.

