# Argus Specification Library

This document is the root index for the Argus specification library. It is written so that a fresh agent can understand the product and implementation target without reading any historical conversation archive.

## Product Summary

Argus is a decision-and-invention engine. A user gives it an ambiguous goal such as a product, growth, UX, technical architecture, or monetization problem. Instead of returning a single brainstorm, Argus should:

1. frame the problem precisely
2. generate diverse candidate solution directions
3. archive and de-duplicate those directions
4. evaluate them against explicit criteria
5. stress-test promising candidates
6. deepen the survivors into executable plans
7. compile a final decision package with multiple bet types and explicit reasoning

Argus is not meant to be a generic chatbot. It is meant to be a search-and-evaluation system with durable memory, reproducible artifacts, and a strong operator workflow.

## Reading Order

| Order | File | Purpose |
| --- | --- | --- |
| 1 | `specs/00-product-north-star.md` | Product mission, users, success criteria, and non-goals |
| 2 | `specs/01-operator-experience.md` | Operator workflow, Ralph loop expectations, and repo ergonomics |
| 3 | `specs/02-system-architecture.md` | Runtime architecture, modules, storage, and interfaces |
| 4 | `specs/03-search-runtime.md` | Search state, actions, frontier policy, and answer compilation |
| 5 | `specs/04-evaluator-and-ranking.md` | Score vectors, hard constraints, ranking logic, and benchmark rules |
| 6 | `specs/05-archive-and-novelty.md` | Archive behavior, dedupe policy, learning compression, and persistence |
| 7 | `specs/06-provider-integration.md` | Codex-first provider integration and future multi-provider expansion |
| 8 | `specs/07-output-artifacts-and-benchmarks.md` | Required artifacts, benchmark dataset shape, and run capture |
| 9 | `specs/08-safety-and-quality-bars.md` | Engineering quality bar, testing rules, and failure handling |

## Implementation Principle

The first implementation target is a Python application that can run locally from the command line and persist all search state to disk. Argus must start with Codex as its main provider, but its internal architecture must make additional CLI providers straightforward. The current provider layer supports Codex, Claude Code, Gemini CLI, and OpenCode behind the same structured action contract.

## Acceptance Condition For A Real First Milestone

Argus reaches its first meaningful milestone when the repository contains:

- a runnable `argus` CLI
- typed domain models matching the core spec objects
- a filesystem-backed run state store
- a working Codex provider wrapper using `codex exec`
- a provider-backed evaluator and semantic novelty judge
- a simple search loop that can frame, generate, score, stress-test, deepen, and compile results
- tests covering the critical control flow
- benchmark fixtures and a harness skeleton
