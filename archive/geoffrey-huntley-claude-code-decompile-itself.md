---
title: "Yes, Claude Code can decompile itself. Here's the source code."
author: Geoffrey Huntley
source: https://ghuntley.com/tradecraft/
date: 2025-03-01
tags:
  - type/analysis
  - topic/ai
  - topic/developer-tools
  - topic/software-development
  - topic/infosec
  - concept/transpilation
  - concept/deobfuscation
  - concept/vibe-coding
  - tech/cursor
  - tech/claude-code
  - tech/llm
  - person/geoffrey-huntley
summary: |
  This article demonstrates the powerful capabilities of Large Language Models (LLMs) in software engineering, specifically their ability to deobfuscate, transpile, and reverse-engineer compiled code. The core thesis is that LLMs can perform clean-room reconstructions of software, even from minified and bundled source code. As a primary example, the author, Geoffrey Huntley, details the process of using an LLM to decompile the `cli.mjs` file from the official `@anthropic-ai/claude-code` npm package, which at the time had no public source code. Key concepts explored include transpilation, deobfuscation, and the "vibe coding" methodology, where the developer guides the AI through a high-level process of specification extraction and code generation.

  This document serves as a practical guide and proof-of-concept for using LLMs to perform complex code-to-spec-to-code transformations. It outlines a multi-stage technique that involves: 1) inspecting the minified JavaScript bundle, 2) prompting an LLM to generate a high-level specification library from the code, 3) using those specs to deobfuscate and split the application into human-readable files, and 4) iteratively implementing the full functionality in a loop. The article also points to a more complex demonstration where a similar process was used to convert a C program to Z/80 assembly and then to a working ZX Spectrum tape, highlighting the versatility of this approach.

  The purpose of this analysis is to illustrate the economic and practical implications of advanced AI in software development. By showing that complex software can be effectively cloned or migrated with commodity tooling and strategic prompting, the author suggests a significant shift in the landscape of software maintenance, auditing, and interoperability. The key takeaway is that the barrier to understanding and rewriting sophisticated software is rapidly decreasing, which has profound consequences for intellectual property, security, and the future of software engineering.
---

# Yes, Claude Code can decompile itself. Here's the source code

---

## Summary

LLMs are now capable of surprisingly strong deobfuscation, transpilation, and structure‑to‑structure conversions. This post highlights a cleanroom reconstruction of the Claude Code npm package via LLM‑driven transpilation and shows that end‑to‑end conversions (e.g., C → ASM → specs → a working Z/80 Spectrum tape) are practical and cheap. The broader implication is that rewriting or cloning complex software becomes increasingly feasible with commodity tooling and careful prompting.

Because the full content is subscriber‑only, this summary focuses on public details and the linked repository.

---

## Key Ideas

- LLMs can perform deobfuscation and cross‑language transpilation effectively.
- A cleanroom transpilation of the official Claude Code package is provided as evidence.
- Demonstrates multi‑stage conversions (e.g., language → assembly → specifications → runnable artifact).
- Implication: software rewriting and migration may be dramatically cheaper and faster.

---

## Source details

- Published: 2025-03-01; Last modified: 2025-08-22
- Author: Geoffrey Huntley
- Tags on source: AI, Software Development, InfoSec, CURSOR, Vibe Coding

---

## Technique (condensed)

1) Install and inspect the npm package

```bash
mkdir claude-code && cd claude-code
npm i @anthropic-ai/claude-code
```

- Locate `node_modules/@anthropic-ai/claude-code/cli.mjs` (minified bundle).
- Strip top comments that trigger safety rails in some LLMs.

2) Initial prompt to produce specs from `cli.mjs`

```text
CLI.js is a commonjs typescript application which has been compiled with webpack.
The symbols have been stripped.
Inspect the source code thoroughly (extra thinking) but skip the SentrySDK source code.
Create a specification library of features of the application.
Convert the source code into human readable.
Keep going until you are done!
```

3) Write out a specification library, then deobfuscate and split by domain

```text
Now deobfuscate the application.
Split the application into separate files per domain in the SPECS folder.
Provide an overview of the directory structure before starting deobfuscation.
Skip the SENTRYSDK.
```

4) Loopback prompt to keep implementing until complete

```text
Look at the SPECS library.
Look at CLAUDE-CODE folder.
Look at @CLI.js (do not confuse it with @cli.ts), keep transpiling and implement anything that's not in the SPECS folder that has not been implemented in the CLAUDE-CODE folder.
```

Notes:

- `cli.mjs` (~5 MB) exceeds typical context windows; persistence and chunking/iteration are required.
- The public Anthropics repo exists but (at the time) contained no source; the cleanroom repo demonstrates feasibility.

---

## Links

- Source post: [Yes, Claude Code can decompile itself. Here's the source code.](https://ghuntley.com/tradecraft/)
- Repository: [ghuntley/claude-code-source-code-transpilation](https://github.com/ghuntley/claude-code-source-code-transpilation)
- Background: [An “oh fuck” moment in time](https://ghuntley.com/oh-fuck/)
- Demo: [C → ASM → specs → Z/80 Speccy tape](https://ghuntley.com/z80/)
- Anthropics repo: [anthropics/claude-code](https://github.com/anthropics/claude-code)
- Socials: [X post](https://x.com/GeoffreyHuntley/status/1895755817082892340), [Bluesky post](https://bsky.app/profile/ghuntley.com/post/3ljcjfbqpsh2k)

---

## Thoughts

If LLMs can reliably traverse code → specs → code loops, then the economics of software maintenance change. Expect faster ports across ecosystems, easier deobfuscation for audit/interop, and mounting pressure on teams to invest in secure generation, provenance, and licensing hygiene.
