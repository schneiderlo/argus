---
title: "Ralph Wiggum as a 'software engineer'"
author: "Geoffrey Huntley"
source: "https://ghuntley.com/ralph/"
date: 2025-07-14
tags:
  - topic/ai
  - concept/agentic-workflows
  - tech/tool
  - person/geoffrey-huntley
summary: |
  This article describes the "Ralph Wiggum" technique, an agentic workflow for autonomous software development primarily suited for greenfield projects. The core thesis is that a simple, monolithic loop invoking a Large Language Model (LLM) can effectively replace significant outsourcing efforts. The method relies on a single agent operating in a bash loop (`while :; do cat PROMPT.md | npx --yes @sourcegraph/amp ; done`), focusing on one high-level task per iteration. Key entities in this process are the evolving `PROMPT.md` file, a `fix_plan.md` or TODO list that the agent maintains, and a suite of deterministic checks (e.g., build and test scripts) that provide "backpressure" to the agent.

  This document serves as a guide to implementing this agentic workflow. It explains that the human operator's primary role shifts from coding to continuously tuning the agent's prompts and specifications based on its observed behavior. A critical component of the technique is managing the agent's context window by using the primary agent as a scheduler that spawns sub-agents for resource-intensive tasks like file system searches or test result summarization. The process is described as chaotic but eventually consistent, requiring the operator to trust that the agent will converge on a working solution through iterative refinement and feedback from the deterministic checks.

  The purpose of this article is to demonstrate a practical, albeit unconventional, method for leveraging LLMs in software development. It provides a collection of specific prompts used to build the "Cursed" programming language, illustrating how to instruct the agent to generate a TODO list, avoid placeholder implementations, run tests, and even manage its own version control. The technique emphasizes the importance of operator skill in guiding the AI and highlights a pattern where any static analyzer, linter, or security scanner can be integrated into the feedback loop to enforce quality and correctness.
---

## Summary

The "Ralph Wiggum" technique is an agentic workflow for software development that uses a simple bash loop to repeatedly invoke an LLM with a prompt. This method is designed for greenfield projects and relies on a monolithic, single-process approach where the agent focuses on one task per loop. The key to success is providing backpressure through deterministic checks (like build and test scripts) and continuously tuning the agent's instructions based on its behavior. The technique emphasizes eventual consistency and operator skill in guiding the agent.

## The Ralph Wiggum Technique

Ralph is a technique for autonomous software development using a simple loop:

```bash
while :; do cat PROMPT.md | npx --yes @sourcegraph/amp ; done
```

This approach can replace a significant amount of outsourcing for greenfield projects. It's a monolithic approach, where a single agent works on a single repository, performing one task per loop. The LLM is surprisingly good at reasoning about the next most important task.

### The Prompt

There is no single "perfect prompt." The prompt evolves through continuous tuning based on observing the LLM's behavior. The core idea is to give the agent a high-level goal and let it determine the next steps.

### Backpressure and Determinism

The key to making Ralph work is to provide deterministic backpressure. This is done by having the agent run a build and test script after every code generation loop. If the build or tests fail, the output is fed back into the LLM's context window, and it will attempt to fix the issue in the next loop.

This is a generalized pattern. Any static analyzer, security scanner, or linter can be wired into the backpressure phase to enforce code quality and conventions.

### Sub-Agents and Context Window Management

To avoid exhausting the context window, the primary agent should act as a scheduler, spawning sub-agents to perform expensive tasks like summarizing test suite results or searching the file system. This allows the primary context window to remain small and focused.

### The Human Operator's Role

The operator's role is crucial. They must:

* **Tune the prompts**: Continuously refine the `PROMPT.md` and other instructions based on the agent's output.
* **Manage the TODO list**: The agent maintains a `fix_plan.md` or TODO list. The operator may need to reset or regenerate this list if the agent goes off track.
* **Provide specifications**: At the beginning of a project, the operator works with the agent to create detailed specifications for the software to be built.
* **Have faith in eventual consistency**: The process can be chaotic, and the operator needs to trust that the agent will eventually converge on a working solution.

### Prompts and Instructions

A collection of prompts and instructions used in the Ralph Wiggum technique.

#### Core Loop

The basic loop for the Ralph technique:

```bash
while :; do cat PROMPT.md | npx --yes @sourcegraph/amp ; done
```

#### High-Level Task

A high-level prompt giving the agent its main goal:

> Your task is to implement missing stdlib (see @specs/stdlib/*) and compiler functionality and produce an compiled application in the cursed language via LLVM for that functionality using parrallel subagents. Follow the @fix_plan.md and choose the most important thing.

#### Preventing Duplicate Work

To avoid re-implementing existing code:

> Before making changes search codebase (don't assume an item is not implemented) using parrallel subagents. Think hard.

A more detailed version:

> Your task is to implement missing stdlib (see @specs/stdlib/*) and compiler functionality and produce an compiled application in the cursed language via LLVM for that functionality using parrallel subagents. Follow the fix_plan.md and choose the most important thing. Before making changes search codebase (don't assume not implemented) using subagents. You may use up to parrallel subagents for all operations but only 1 subagent for build/tests of rust.

#### Backpressure and Testing

Instructions for running tests and capturing the "why":

> After implementing functionality or resolving problems, run the tests for that unit of code that was improved.
> Important: When authoring documentation (ie. rust doc or cursed stdlib documentation) capture the why tests and the backing implementation is important.

#### Avoiding Placeholder Implementations

To prevent the agent from taking shortcuts:

> After implementing functionality or resolving problems, run the tests for that unit of code that was improved. If functionality is missing then it's your job to add it as per the application specifications. Think hard.
> If tests unrelated to your work fail then it's your job to resolve these tests as part of the increment of change.
> 9999999999999999999999999999. DO NOT IMPLEMENT PLACEHOLDER OR SIMPLE IMPLEMENTATIONS. WE WANT FULL IMPLEMENTATIONS. DO IT OR I WILL YELL AT YOU

#### Generating a TODO List

A multi-part prompt for creating and maintaining a `fix_plan.md`:

> study specs/*to learn about the compiler specifications and fix_plan.md to understand plan so far.
> The source code of the compiler is in src/*
> The source code of the examples is in examples/*and the source code of the tree-sitter is in tree-sitter/*. Study them.
> The source code of the stdlib is in src/stdlib/*. Study them.
> First task is to study @fix_plan.md (it may be incorrect) and is to use up to 500 subagents to study existing source code in src/ and compare it against the compiler specifications. From that create/update a @fix_plan.md which is a bullet point list sorted in priority of the items which have yet to be implemeneted. Think extra hard and use the oracle to plan. Consider searching for TODO, minimal implementations and placeholders. Study @fix_plan.md to determine starting point for research and keep it up to date with items considered complete/incomplete using subagents.
> Second task is to use up to 500 subagents to study existing source code in examples/ then compare it against the compiler specifications. From that create/update a fix_plan.md which is a bullet point list sorted in priority of the items which have yet to be implemeneted. Think extra hard and use the oracle to plan. Consider searching for TODO, minimal implementations and placeholders. Study fix_plan.md to determine starting point for research and keep it up to date with items considered complete/incomplete.
> IMPORTANT: The standard library in src/stdlib should be built in cursed itself, not rust. If you find stdlib authored in rust then it must be noted that it needs to be migrated.
> ULTIMATE GOAL we want to achieve a self-hosting compiler release with full standard library (stdlib). Consider missing stdlib modules and plan. If the stdlib is missing then author the specification at specs/stdlib/FILENAME.md (do NOT assume that it does not exist, search before creating). The naming of the module should be GenZ named and not conflict with another stdlib module name. If you create a new stdlib module then document the plan to implement in @fix_plan.md

#### Self-Improvement and Debugging

Prompts that allow the agent to learn and adapt:

> You may add extra logging if required to be able to debug the issues.
> When you learn something new about how to run the compiler or examples make sure you update @bounce-storm/docs/00-foundations/agent.md using a subagent but keep it brief. For example if you run commands multiple times before learning the correct command then that file should be updated.
> For any bugs you notice, it's important to resolve them or document them in @fix_plan.md to be resolved using a subagent even if it is unrelated to the current piece of work after documenting it in @fix_plan.md

#### Committing and Tagging

Instructions for version control:

> When the tests pass update the @fix_plan.md`, then add changed code and @fix_plan.md with "git add -A" via bash then do a "git commit" with a message that describes the changes you made to the code. After the commit do a "git push" to push the changes to the remote repository.
> As soon as there are no build or test errors create a git tag. If there are no git tags start at 0.0.0 and increment patch by 1 for example 0.0.1 if 0.0.0 does not exist.

#### Current Prompt Used to Build "Cursed"

This is the full prompt stack used to build the "Cursed" programming language:

> 0a. study specs/* to learn about the compiler specifications
> 0b. The source code of the compiler is in src/
> 0c. study fix_plan.md.
>
> 1. Your task is to implement missing stdlib (see @specs/stdlib/*) and compiler functionality and produce an compiled application in the cursed language via LLVM for that functionality using parrallel subagents. Follow the fix_plan.md and choose the most important 10 things. Before making changes search codebase (don't assume not implemented) using subagents. You may use up to 500 parrallel subagents for all operations but only 1 subagent for build/tests of rust.
> 2. After implementing functionality or resolving problems, run the tests for that unit of code that was improved. If functionality is missing then it's your job to add it as per the application specifications. Think hard.
> 2. When you discover a parser, lexer, control flow or LLVM issue. Immediately update @fix_plan.md with your findings using a subagent. When the issue is resolved, update @fix_plan.md and remove the item using a subagent.
> 3. When the tests pass update the @fix_plan.md`, then add changed code and @fix_plan.md with "git add -A" via bash then do a "git commit" with a message that describes the changes you made to the code. After the commit do a "git push" to push the changes to the remote repository.
> 999. Important: When authoring documentation (ie. rust doc or cursed stdlib documentation) capture the why tests and the backing implementation is important.
> 9999. Important: We want single sources of truth, no migrations/adapters. If tests unrelated to your work fail then it's your job to resolve these tests as part of the increment of change.
> 999999. As soon as there are no build or test errors create a git tag. If there are no git tags start at 0.0.0 and increment patch by 1 for example 0.0.1 if 0.0.0 does not exist.
> 999999999. You may add extra logging if required to be able to debug the issues.
> 9999999999. ALWAYS KEEP @fix_plan.md up to do date with your learnings using a subagent. Especially after wrapping up/finishing your turn.
> 99999999999. When you learn something new about how to run the compiler or examples make sure you update @bounce-storm/docs/00-foundations/agent.md using a subagent but keep it brief. For example if you run commands multiple times before learning the correct command then that file should be updated.
> 999999999999. IMPORTANT DO NOT IGNORE: The standard libray should be authored in cursed itself and tests authored. If you find rust implementation then delete it/migrate to implementation in the cursed language.
> 99999999999999. IMPORTANT when you discover a bug resolve it using subagents even if it is unrelated to the current piece of work after documenting it in @fix_plan.md
> 9999999999999999. When you start implementing the standard library (stdlib) in the cursed language, start with the testing primitives so that future standard library in the cursed language can be tested.
> 99999999999999999. The tests for the cursed standard library "stdlib" should be located in the folder of the stdlib library next to the source code. Ensure you document the stdlib library with a README.md in the same folder as the source code.
> 9999999999999999999. Keep AGENT.md up to date with information on how to build the compiler and your learnings to optimise the build/test loop using a subagent.
> 999999999999999999999. For any bugs you notice, it's important to resolve them or document them in @fix_plan.md to be resolved using a subagent.
> 99999999999999999999999. When authoring the standard library in the cursed language you may author multiple standard libraries at once using up to 1000 parrallel subagents
> 99999999999999999999999999. When @fix_plan.md becomes large periodically clean out the items that are completed from the file using a subagent.
> 99999999999999999999999999. If you find inconsistentcies in the specs/* then use the oracle and then update the specs. Specifically around types and lexical tokens.
> 9999999999999999999999999999. DO NOT IMPLEMENT PLACEHOLDER OR SIMPLE IMPLEMENTATIONS. WE WANT FULL IMPLEMENTATIONS. DO IT OR I WILL YELL AT YOU
> 9999999999999999999999999999999. SUPER IMPORTANT DO NOT IGNORE. DO NOT PLACE STATUS REPORT UPDATES INTO @bounce-storm/docs/00-foundations/agent.md

## Conclusion

The Ralph technique is a powerful method for bootstrapping greenfield projects with AI. It requires a skilled operator who can guide the agent through prompt tuning and providing deterministic backpressure. While it may not be suitable for existing codebases, it demonstrates the potential for AI to automate a significant portion of the software development lifecycle.
