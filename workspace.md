Design a workspace + execution + integration system for a “code factory” where 10 to 50 AI agents run tasks concurrently on the same repository.

## Goal

Produce a system design that enables many agents to work in parallel with extremely fast startup, strong isolation, shared dependency acceleration, and an efficient way to aggregate, validate, and merge the outputs of multiple agents.

## Core problem

Independent workspaces cause repeated download/extract/index/build of common dependencies, especially when many agents start at once.

Examples:

- Node.js: `node_modules`, pnpm store, yarn cache, npm cache, framework build caches
- Python: virtualenvs, wheel caches, pip caches, uv caches
- Rust: cargo registry, git deps, target build artifacts
- C/C++: compiler caches, object files, precompiled headers, Conan/vcpkg/homegrown dependency trees
- Bazel: repository cache, external dependency fetches, action cache, disk cache, output base
- CMake: configure trees, `build/` directories, generated Ninja/Make files, compiler discovery/configuration artifacts

This creates major disk I/O, CPU, and startup contention.

## Hard requirements

The design must satisfy all of the following:

### Workspace and execution

R1. Workspace creation time: {{WORKSPACE_STARTUP_TARGET}} (default: < 1s).  
R2. Shared dependency caches across tasks, but no cross-task contamination.  
R3. Strict isolation: task A cannot read or modify task B’s workspace artifacts.  
R4. Perfect auditability: server-owned VCS and immutable provenance for every change.  
R5. Reproducibility: any task workspace can be reconstructed exactly from the audit trail.  
R6. Safety: tasks may execute untrusted code; assume Linux hosts.

### Multi-agent coordination and aggregation

R7. Efficient aggregation of work from many agents: the system must support collecting, comparing, validating, rebasing, and merging outputs from 10 to 50 concurrent agents without creating a serial bottleneck.  
R8. Conflict handling: the system must define how overlapping edits are detected early, how semantic or textual conflicts are surfaced, and how conflicting work is resolved or re-planned.  
R9. Incremental integration: the system must support staged promotion of agent outputs through validation gates rather than requiring one final “big bang” merge.  
R10. Deterministic merge provenance: every integrated result must record which agent produced which change, from what base snapshot, under what policy, with what validation results.  
R11. Scalable review/selection: when multiple agents attempt the same or similar task, the system must support ranking, deduplication, best-of-N selection, or synthesis without excessive human intervention.  
R12. Failure containment: if one agent produces bad code, malicious output, or an invalid patch, that output must be quarantined without slowing or corrupting the rest of the system.

### Build-system-specific requirements

R13. The design must explicitly cover safe cache sharing and invalidation behavior for Node.js, Python, Rust, C/C++, Bazel, and CMake-based builds.  
R14. The design must distinguish immutable shared artifacts from task-private writable state for each ecosystem.  
R15. The design must explain handling of compiler caches, generated files, configure outputs, toolchain discovery, external repository fetching, and lockfile-like dependency state across concurrent tasks.  
R16. The design must explain how remote execution, remote cache, or distributed build features are used or intentionally avoided for Bazel/C++ workloads.  
R17. The design must address correctness hazards specific to native builds, including ABI drift, toolchain variance, nondeterministic build outputs, host contamination, and generated header/source races.

## Assumptions

- Linux execution hosts
- Monorepo or large polyrepo checkout is possible
- Agents may run build/test/lint/codegen commands
- Repositories may contain mixed build systems, including npm/pnpm/yarn, Python tooling, Cargo, CMake, and Bazel
- Agents may be assigned independent or overlapping tasks
- The control plane is trusted
- Agent runtimes and executed task code are not trusted
- Git is the source-of-truth VCS unless you strongly justify an alternative
