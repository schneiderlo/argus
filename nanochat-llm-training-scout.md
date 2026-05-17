Argus research request:

Use the coverage-led research runtime to discover, compare, and prioritize
high-upside LLM-training experiments for `karpathy/nanochat`.

This is not a request for a single generic brainstorm. Treat it as a structured search
over proposal families. Frame the search space, seed materially different families,
triage weak or already-crowded directions, deepen the strongest survivors, red-team
them, and write a final decision memo that a serious experimenter could act on.

## Experimental Ground

The target implementation surface is `karpathy/nanochat`, especially:

- pretraining in `scripts/base_train.py`
- model internals in `nanochat/gpt.py`
- evaluation via `val_bpb` / CORE
- optionally SFT/RL in `scripts/chat_sft.py` and `scripts/chat_rl.py`

Assume nanochat is a small, hackable LLM-training codebase where speedrun relevance,
line-count, wall-clock, and clean ablation design matter. Prefer ideas that can be
implemented as controlled deltas rather than broad system rewrites.

## Target Decision

Choose the best portfolio of cross-domain experiments that could plausibly produce a
meaningful nanochat speedrun or quality improvement.

The final recommendation should identify:

- the first 3 experiments to implement
- the most publishable ideas if they work
- the ideas most likely to improve wall-clock speedrun results
- the ideas most likely to be genuinely novel but hard
- a 2-week experiment roadmap

## Research Theme

Find "Canny edge detector"-style transfers: simple observations from another field
that become powerful mathematical rules when translated correctly into LLM training.

Do not stay inside computer vision. Cover at least these domains during search-space
framing and seeding:

- gauge theory / symmetry / canonicalization
- tensor-network canonical forms
- optimal experimental design
- matched filters / lock-in amplifiers
- Kalman filtering / control
- renormalization group
- robust statistics
- error-correcting codes
- active learning
- numerical PDE / adaptive mesh refinement
- thermodynamics / nonequilibrium systems
- neuroscience memory replay
- signal processing
- statistical mechanics
- information theory
- numerical analysis
- dynamical systems
- econometrics
- chemistry / biology
- fluid mechanics

## Hard Gates

Reject or down-rank proposal families that fail any of these gates:

- The idea is only a metaphor with no implementable nanochat mechanism.
- The idea merely renames a known trick without a substantive new variant.
- The implementation path cannot be localized to plausible nanochat hooks.
- The experiment cannot be falsified with clear metrics and baselines.
- The proposal depends on unverifiable claims but does not mark them as uncertainty.
- The expected code change is too large for a speedrun-oriented first test unless the
  upside is exceptional.

## Decision Criteria

Argus has separate judges for scoring, triage, and final comparison. Do not force a
manual scoring formula inside proposal text. Instead, make every proposal easy for
those judges to evaluate by preserving clear evidence about:

- potential upside
- novelty and prior-art saturation
- nanochat feasibility
- speedrun relevance
- expected code complexity: tiny / small / medium / large
- best target: pretraining, optimizer, data selection, architecture, SFT, RL, inference, evaluation
- concrete failure modes and falsifiable uncertainty

## Required Coverage Axes

When framing the search space, create coverage cells that separate ideas by mechanism,
not just source-domain label. Include cells for:

- optimizer / update geometry
- data selection / curriculum / sampling
- loss shaping / evaluation targeting
- architecture / parameterization
- precision / stability / fp8 behavior
- SFT/RL feedback loops
- inference-time or evaluation-time methods
- experimental-design and ablation strategy

Also separate quick-win cells from moonshot cells.

## Known-Trick Collision Policy

Avoid weak ideas that merely rename known LLM tricks. For any proposal resembling
focal loss, RHO-Loss, Rho-1 / selective language modeling, DoReMi, curriculum learning,
AGC, ZClip, AdaGC, schedule-free optimization, Muon, K-FAC, natural gradient, sparse
attention, contrastive decoding, replay buffers, or active learning, explicitly say:

- what it resembles
- whether the surrounding prior art is crowded or sparse
- what new variant would be needed to make the nanochat experiment nontrivial

## Source And Evidence Discipline

For source-dependent claims, prefer primary sources:

- papers
- official repos
- official docs
- benchmark or implementation artifacts from the relevant project

Do not fabricate citations. Instead:

- cite only sources you can identify confidently
- label source leads that require verification as `verification_needed`
- prefer primary-source targets: papers, official repos, official docs
- lower evidence quality and confidence when prior-art status is uncertain
- be brutally honest about novelty and prior-art saturation

Tone:

Be imaginative but rigorous. Prefer precise mechanisms, formulas, nanochat hooks, and
falsifiable experiments over analogies. Do not hype metaphor-only ideas.
