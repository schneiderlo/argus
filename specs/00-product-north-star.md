# Product North Star

## Purpose

Argus exists to help a serious builder make better bets than they would have made alone. The system should take ambiguous requests and return structured, decision-ready outputs with explicit tradeoffs, not generic ideation fluff.

## Core Promise

Given a request, Argus must do more than brainstorm. It must:

1. clarify the true problem
2. explore a broad but controlled solution space
3. preserve diversity instead of collapsing too early
4. identify promising branches
5. attack weak assumptions early
6. deepen only the best survivors
7. return an answer package that is useful for action

## Primary Users

- product founders and product leads
- staff and principal engineers designing systems or internal platforms
- operators exploring growth, retention, monetization, or workflow bets
- researchers or strategists who need explicit alternatives and reasoning

## User Input Shape

The initial input can be messy. Examples:

- "Find the best retention strategy for this workflow-heavy B2B product."
- "Design a new feature family that creates a moat for prosumers without hurting onboarding."
- "Propose the best architecture for a local-first brainstorming engine under these constraints."

Argus must treat the first user request as incomplete. Problem framing is mandatory, not optional.

## Output Shape

The minimum final answer package must include:

- a refined problem frame
- the best overall recommendation
- a conservative option
- a high-upside option
- a short list of rejected alternatives that still taught the system something
- explicit assumptions
- explicit failure modes
- a proposed first experiment or implementation plan
- reasons the system could be wrong

## Success Criteria

Argus is succeeding when:

- outputs are materially more useful than a single-shot model response
- alternatives are meaningfully distinct instead of paraphrases
- weak or decorative ideas are pruned early
- the final recommendation includes executable next steps
- the system can reproduce a run and explain why a branch won

## Non-Goals

The initial versions of Argus should not try to be:

- a general autonomous coding platform
- a generic multi-agent shell
- a chat UI with no structured state
- a slide generator
- a broad research assistant with weak evaluation

## Product Philosophy

- evaluator-first beats eloquence-first
- search beats panel-chat theater
- archived stepping stones beat single-winner greediness
- diversity matters because premature convergence produces mediocre answers
- structured artifacts matter because the operator must be able to audit the run

