## Goal

Find the best browser game concept to win the 2026 Cursor AI Vibe Coding Game Jam.

I want the output to identify the strongest idea to actually ship in time and
maximize both:

- odds of winning with judges
- odds of going viral with players, streamers, and social clips

## Context

- Deadline: 1 May 2026 at 13:37 UTC.
- The game will be built starting now, not from an old project.
- At least 90% of the code will be written by AI.
- The game must be free-to-play, playable on the web, and require no login or signup.
- Instant access matters a lot: no heavy downloads, no loading screen, no long setup.
- Multiplayer is preferred by the jam host, but not strictly required.
- The implementation stack is already decided:
  - C++
  - WebAssembly
  - WebGPU
- The engine/runtime work is already handled. Do not spend meaningful time proposing engine architecture unless it directly changes the viability of the idea.

## What I Need

I do not want generic "make a multiplayer party game" advice.

I want a sharp search over game concepts that are:

- immediately legible in the first 3 seconds
- fun or intriguing in the first 20 seconds
- highly clip-able and shareable
- visually distinctive enough to stand out in a feed
- feasible for a single focused AI-heavy build effort in under a month
- strong on desktop web and still reasonably playable on laptop-class hardware
- compatible with near-instant start in browser

## Hard Constraints

Any recommended concept must satisfy all of the following:

- Browser-first and frictionless: open the page and basically start playing immediately.
- No account creation, login wall, or required install.
- No giant initial asset download.
- The core loop must be understandable without tutorial text walls.
- Scope must be realistic for one month with an already-existing engine but without assuming a large human content team.
- The concept should not depend on a huge handcrafted campaign, thousands of bespoke assets, or deep live-ops.
- If multiplayer is used, it should improve virality and spectatability rather than add complexity for its own sake.
- The idea should have a strong "watch one clip, instantly want to try it" quality.

## Important Strategic Assumptions

- I care more about a game that feels fresh, surprising, and socially contagious than about a technically "impressive but dry" demo.
- I care more about one excellent jam-sized game than a broad platform or tool.
- I am willing to trade some depth for a brutally strong hook, as long as the game is not a one-joke throwaway.
- A concept that creates memorable stories, betrayals, reversals, close calls, public chaos, or ego-driven competition will usually score higher than a polished but emotionally flat experience.
- WebGPU/C++/WASM should be treated as leverage for responsiveness, spectacle, simulation density, or visual identity, not as the product itself.

## What To Explore

Search broadly, but prioritize concepts that combine several of these:

1. **Instant readability**
   The fantasy and control scheme should be obvious almost immediately.

2. **Viral loop**
   The game should naturally produce moments players want to clip, share, challenge friends with, or stream.

3. **Session design**
   Best target is something that works in 30 seconds to 5 minutes per run or match, with strong replayability.

4. **Social energy**
   Explore asymmetric multiplayer, drop-in public lobbies, crowd chaos, sabotage, bluffing, racing, survival pressure, physics comedy, score-chasing, or creator-friendly challenge formats.

5. **Visual signature**
   The game should have a memorable visual premise or motion pattern that stands out in a silent autoplay feed.

6. **Jam execution reality**
   The winning candidate must still be practical to build, tune, and polish before the deadline.

## Evaluation Criteria

When comparing concepts, score them explicitly on:

- **Virality potential**: likelihood of organic sharing, clips, dares, friend-invites, or stream appeal.
- **Judge appeal**: how likely the concept is to feel memorable, modern, and "ahead" of typical AI-jam output.
- **Instant-start suitability**: how compatible it is with tiny onboarding and fast browser entry.
- **Multiplayer leverage**: whether multiplayer meaningfully improves the game's ceiling.
- **Prototype speed**: how quickly a compelling first playable can exist.
- **Polishability in one month**: whether the game can be made tight enough to actually submit with confidence.
- **Visual distinctiveness**: whether a gif or 10-second video would look different from common jam games.
- **Retention after the hook**: whether players have a reason to play again after the first joke or surprise.
- **Engine-fit**: whether C++/WASM/WebGPU provides real advantage to this concept.

## Failure Modes To Avoid

Penalize ideas that drift into any of these traps:

- "Technically cool engine demo" more than "must-play game"
- over-scoped multiplayer backend burden
- content-hungry genres that need dozens of levels or lots of authored assets
- clever but low-emotion ideas with weak spectator value
- slow-burn strategy games that are hard to understand from a clip
- games that are fun only after a long tutorial
- ideas that look like generic surviv.io / agar.io / party-game clones with a thin twist
- ideas whose best feature depends on future polish rather than the first playable

## Required Output Shape

Produce:

1. The **best overall concept to ship**
2. One **conservative but high-probability** option
3. One **high-upside risky** option
4. A short list of rejected ideas that seemed tempting but are strategically worse

For the best overall concept, include:

- the one-sentence pitch
- the first 10 seconds of player experience
- the core loop
- why people would share it
- why judges would remember it
- whether it should be multiplayer or single-player
- the minimum lovable version for the jam
- the art/motion/visual identity direction
- the biggest risks
- the fastest prototype milestone
- a realistic feature cut line

Also include a shortlist of 5-10 candidate concepts before narrowing, so the search does not collapse too early.

## Extra Emphasis

I especially want concepts that feel:

- born for the internet
- easy to challenge friends with
- good in a single screenshot or gif
- capable of generating stories people retell
- polished enough to feel like a real product, not just an AI experiment

If the strongest answer is not multiplayer, explain why it still beats multiplayer options.
