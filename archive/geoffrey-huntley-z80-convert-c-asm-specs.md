---
title: "Can a LLM convert C, to ASM to specs and then to a working Z/80 Speccy tape? Yes."
author: Geoffrey Huntley
source: https://ghuntley.com/z80/
date: 2025-03-02
tags:
  - type/analysis
  - topic/ai
  - topic/developer-tools
  - topic/software-development
  - concept/specifications
  - concept/transpilation
  - tech/cursor
  - tech/llm
  - tech/z80
  - person/geoffrey-huntley
summary: |
  This article demonstrates a powerful, end-to-end application of Large Language Models (LLMs) in legacy system engineering, showing their capability to transpile code across vastly different architectures. The core thesis is that LLMs can execute a complete, multi-stage conversion pipeline: from high-level C source code, to compiled assembly, to a high-level functional specification, and finally to a working program for a vintage Z/80-based computer. The process begins with a simple C program (a sales tax calculator), which is compiled and then disassembled into x86 assembly using `objdump`. This assembly code is then fed to an LLM to reverse-engineer a clean, platform-agnostic specification of its behavior.

  This document serves as a case study in specification-first, AI-driven development and porting. After deriving the functional specs from the assembly, the author uses the LLM to implement those specs in Z/80 assembly language, specifically targeting the ZX Spectrum. The generated assembly is then compiled into a `.tap` tape image using the `pasmo` assembler. The process is iterative, employing a "loopback" workflow where screenshots and error logs from a ZX Spectrum emulator are fed back to the LLM to debug and refine the Z/80 code until it functions correctly. This highlights the LLM's ability to work with visual feedback and handle low-level machine details like I/O and arithmetic on an 8-bit processor.

  The purpose of this demonstration is to prove that clean-room rewrites and cross-platform ports of legacy software are now practical and inexpensive with modern AI tooling. By successfully creating a working program for a 40-year-old computer from modern C code, the author, Geoffrey Huntley, reinforces the idea that the economic barriers to software migration and reverse-engineering are collapsing. The article also references a real-world replication of this technique by Daniel Joyce, who ported the `ls` command to Rust, further validating the feasibility of this LLM-driven transpilation workflow.
---

# Can a LLM convert C, to ASM to specs and then to a working Z/80 Speccy tape? Yes

---

## Summary

Demonstrates an end‑to‑end pipeline: C source → compiled binary → objdump assembly → high‑level specs → working Z/80 Spectrum program. The post shows how iterative prompting, decompilation/transpilation, and a specification‑first workflow can produce a functional Speccy tape, reinforcing that clean‑room rewrites and cross‑platform ports are now practical and cheap with LLMs.

---

## Source details

- Published: 2025-03-02; Last modified: 2025-08-25
- Author: Geoffrey Huntley
- Tags on source: AI, Software Development, CURSOR, Vibe Coding

---

## Highlights

- Starts from a toy C program (sales tax calculator), compiles with `gcc`, then `objdump -d` to obtain assembly.
- Prompts the LLM to extract a specification library from assembly output (functional overview, data flow, business rules).
- Normalizes the specs to remove C‑isms; uses them to target Z/80.
- Generates a ZX Spectrum assembly implementation and builds a `.tap` image with `pasmo`.
- Iterative loop with screenshots/logs to fix issues (e.g., input handling, tax calculation) until the Speccy program works.
- Mentions real‑world replication: Daniel Joyce ported `ls` to Rust via `objdump` techniques ([DanielJoyce/ls-rs](https://github.com/DanielJoyce/ls-rs)).

---

## Technique (condensed)

1) Seed the LLM with a simple C program
   - Compile: `gcc calc.c -o calc`
   - Disassemble: `objdump -d calc > calc.asm`

2) Derive specifications from assembly
   - Prompt: generate functional overview, data flow, and business logic specs from `calc.asm`.

3) De‑C‑ify the specs
   - Prompt: remove ANSI C specifics; keep domain‑level behavior only.

4) Target Z/80 Spectrum
   - Prompt: implement as Z/80 program; compile with `pasmo --tapbas taxcalc.asm taxcalc.tap`; run in emulator.

5) Close the loop
   - Use screenshots and logs to guide corrections (I/O handling, formatting, arithmetic) until green.

---

## Links

- Source post: [Can a LLM convert C, to ASM to specs and then to a working Z/80 Speccy tape? Yes.](https://ghuntley.com/z80/)
- Related: [Yes, Claude Code can decompile itself. Here's the source code.](https://ghuntley.com/tradecraft/)
- Example: [DanielJoyce/ls-rs](https://github.com/DanielJoyce/ls-rs)
- Socials: [X post](https://x.com/GeoffreyHuntley/status/1896154477872505246), [Bluesky](https://bsky.app/profile/ghuntley.com/post/3ljfbuvpojd2a), [LinkedIn](https://www.linkedin.com/posts/geoffreyhuntley_can-an-llm-convert-c-to-asm-to-specs-and-activity-7301919526856663040-ZkvV)
