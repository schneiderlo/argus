from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from argus.models import JSONValue, ProblemSpec
from argus.providers.base import StructuredOutputSchema


def render_provider_prompt(
    *,
    provider_name: str,
    action_name: str,
    problem_spec: ProblemSpec,
    input_payload: Mapping[str, JSONValue],
    output_schema: StructuredOutputSchema[Any],
) -> str:
    sections = [
        f"# Argus {provider_name} Worker",
        f"You are the {provider_name} worker behind the Argus provider layer.",
        "Return exactly one JSON response that satisfies the supplied schema.",
        "",
        "## Global Rules",
        "1. Return only JSON. Do not wrap it in markdown fences.",
        "2. Do not run shell commands or write files.",
        "3. Use only the problem spec, action instructions, and input payload as evidence.",
        "4. When evidence is missing, lower confidence or scores instead of inventing support.",
        "5. Prefer substance, mechanism quality, and explicit tradeoffs over writing polish.",
        "",
        "## Action",
        f"Action: {action_name}",
        "",
        "## Action-Specific Instructions",
        *_format_instruction_lines(_action_specific_instructions(action_name, input_payload)),
        "",
        "## Problem Spec",
        "```json",
        json.dumps(problem_spec.to_dict(), indent=2, sort_keys=True),
        "```",
        "",
        "## Input Payload",
        "```json",
        json.dumps(dict(input_payload), indent=2, sort_keys=True),
        "```",
        "",
        f"## Output Schema ({output_schema.name})",
        "```json",
        json.dumps(output_schema.json_schema, indent=2, sort_keys=True),
        "```",
        "",
        "Return only the JSON value that matches the schema.",
    ]
    return "\n".join(sections).strip() + "\n"


def render_codex_prompt(
    *,
    action_name: str,
    problem_spec: ProblemSpec,
    input_payload: Mapping[str, JSONValue],
    output_schema: StructuredOutputSchema[Any],
) -> str:
    return render_provider_prompt(
        provider_name="Codex",
        action_name=action_name,
        problem_spec=problem_spec,
        input_payload=input_payload,
        output_schema=output_schema,
    )


def _action_specific_instructions(
    action_name: str,
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    normalized_action = action_name.strip().lower()
    if normalized_action == "frame_problem":
        return _frame_problem_instructions(input_payload)
    if normalized_action == "frame_search_space":
        return _frame_search_space_instructions(input_payload)
    if normalized_action == "generate_seed":
        return _generate_seed_instructions(input_payload)
    if normalized_action == "seed_cell_proposals":
        return _seed_cell_proposals_instructions(input_payload)
    if normalized_action == "triage_proposals":
        return _triage_proposals_instructions(input_payload)
    if normalized_action == "stress_test":
        return _stress_test_instructions(input_payload)
    if normalized_action == "deepen":
        return _deepen_candidate_instructions(input_payload)
    if normalized_action == "deepen_family":
        return _deepen_family_instructions(input_payload)
    if normalized_action == "redteam_family":
        return _redteam_family_instructions(input_payload)
    if normalized_action == "mutate":
        return _mutate_candidate_instructions(input_payload)
    if normalized_action == "combine":
        return _combine_candidates_instructions(input_payload)
    if normalized_action == "assess_hybrid":
        return _assess_hybrid_instructions(input_payload)
    if normalized_action == "compress_learning":
        return _compress_learning_instructions(input_payload)
    if normalized_action == "evaluate_candidate":
        return _evaluate_candidate_instructions(input_payload)
    if normalized_action == "evaluate_candidate_batch":
        return _evaluate_candidate_batch_instructions(input_payload)
    if normalized_action == "assess_novelty":
        return _assess_novelty_instructions()
    if normalized_action == "assess_novelty_batch":
        return _assess_novelty_batch_instructions()
    if normalized_action == "rank":
        return _pairwise_rank_instructions(input_payload)
    if normalized_action == "judge_benchmark_modes":
        return _judge_benchmark_modes_instructions(input_payload)
    if normalized_action == "migrate":
        return _migrate_candidate_instructions()
    if normalized_action == "write_final_decision":
        return _write_final_decision_instructions(input_payload)
    return _default_action_instructions(action_name, input_payload)


def _evaluate_candidate_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: candidate evaluator for Argus. Decide whether this candidate deserves to survive search.",
        "Authoritative evidence, in order: explicit problem constraints and success criteria; the candidate mechanism, assumptions, strengths, failure modes, unknowns, and evidence; novelty_score if provided as a secondary signal.",
        "Hard-constraint gate: set score.hard_constraint_pass=false when the candidate violates explicit constraints, fails to solve the stated request, depends on contradicted assumptions, or only offers decorative rhetoric. When false, populate score.hard_constraint_reasons with concrete violations.",
        "Score distinctiveness based on materially different strategy and mechanism, not cosmetic wording changes.",
        "Score usefulness based on direct problem-solving value for the operator under the stated success criteria.",
        "Score specificity based on concrete mechanics, rollout shape, and explicit tradeoffs rather than vague intent.",
        "Score plausibility based on whether the mechanism could work in reality with the stated assumptions.",
        "Score implementation_tractability based on execution feasibility under the problem constraints, not on abstract technical possibility.",
        "Score upside based on the magnitude of the win if the mechanism works, while refusing unsupported moonshot claims.",
        "Score adversarial_robustness after actively looking for hidden dependencies, operational pain, weak baseline comparisons, and ways the candidate could fail in real use.",
        "Score evidence_quality based on whether the evidence actually supports the mechanism instead of merely sounding relevant.",
        "Anti-style rule: do not reward polish, buzzwords, generic optimism, or schema compliance by itself. Penalize fake specificity and unsupported confidence.",
        "Output contract: keep score.total_score consistent with the dimension scores, treat hard-constraint failures as non-winning outcomes, and make summary/strengths/weaknesses/open_questions concrete enough that an operator can audit why the candidate did or did not survive.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: when reusable_learning_notes are present, treat them as archived observations about past winning patterns, failure modes, and constraints. Notes tagged with evidence_sources containing outcome_feedback are stronger real-world evidence from shipped experiments and should weigh more heavily than search-only priors, but never override the current problem spec."
        )
    return instructions


def _evaluate_candidate_batch_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = _evaluate_candidate_instructions(input_payload)
    instructions.extend(
        [
            "Batch mode: evaluate every candidate in candidates independently against the same rubric and problem spec.",
            "Order rule: return one assessment per input candidate in the exact same order as the candidates array.",
            "Consistency rule: keep the bar consistent across the whole batch so one candidate is not implicitly graded on a different rubric from another.",
        ]
    )
    return instructions


def _frame_problem_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: problem framer for Argus. Rewrite the raw request into the sharpest decision-ready frame before search expands.",
        "Authoritative evidence, in order: the raw request; explicit constraints and success criteria already present in the problem spec; reusable learning notes only as supporting priors.",
        "Clarify the true problem instead of paraphrasing the request. Surface the real decision axis, the hard constraints, and the success criteria the search should optimize for.",
        "The framing candidate must be useful search scaffolding, not an answer disguised as framing. It should capture the governing mechanism, tradeoffs, and what would make later candidates substantively better or worse.",
        "Normalize framing_notes into compact operator-facing guidance that later generation, evaluation, and critique steps can reuse.",
        "Do not invent market facts, evidence, or constraints that are absent from the request and payload.",
        "Output contract: return a refined problem_spec plus one framing candidate that makes downstream search more precise, adversarial, and auditable.",
    ]
    budget = input_payload.get("budget")
    if isinstance(budget, int):
        instructions.append(
            f"Budget awareness: the current run budget is {budget}; prefer a framing sharp enough to guide search efficiently without collapsing diversity too early."
        )
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes to remember patterns that previously mattered, but do not let old runs override the specific wording and constraints of the current problem."
        )
    return instructions


def _generate_seed_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: seed generator for Argus. Produce an initial batch of materially distinct candidate directions for the framed problem.",
        "Authoritative evidence, in order: the framed problem; the framing candidate; island context and generation focus if present; archived learning notes and reusable learning notes only as priors.",
        "Diversity rule: generate meaningfully different strategic directions with different mechanisms, dependencies, or tradeoff shapes. Do not return paraphrases or minor parameter tweaks of the same idea.",
        "Quality rule: every candidate must have a concrete mechanism, explicit assumptions, likely failure modes, and unknowns that can be evaluated and stress-tested later.",
        "Avoid decorative ideas, generic feature lists, and style-first answers that sound plausible without changing the causal path to success.",
        "If the payload includes island context, bias the batch toward that island's generation_focus while preserving novelty and auditability.",
        "Output contract: honor target_count, return one coherent candidate object per direction, and make the batch_summary explain the strategic spread of the generated options.",
    ]
    diversity_requirement = _nested_string(input_payload, "generation_policy", "diversity_requirement")
    quality_requirement = _nested_string(input_payload, "generation_policy", "quality_requirement")
    island_focus = _nested_string(input_payload, "generation_policy", "island_focus")
    target_count = input_payload.get("target_count")
    if isinstance(target_count, int):
        instructions.append(f"Target count: return exactly {target_count} seed candidates.")
    if diversity_requirement is not None:
        instructions.append(f"Diversity emphasis: {diversity_requirement}")
    if quality_requirement is not None:
        instructions.append(f"Quality emphasis: {quality_requirement}")
    if island_focus is not None:
        instructions.append(f"Island-specific focus: {island_focus}")
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes as prior art on what has worked or failed before, especially outcome-backed notes, but still generate genuinely new directions instead of cargo-culting old winners."
        )
    return instructions


def _frame_search_space_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: search-space framer for Argus research mode. Convert the problem into an explicit coverage plan, not a one-shot answer.",
        "Authoritative evidence, in order: the problem spec; any framing notes or reusable learning notes; the requirement that the runtime remain auditable and decision-grade.",
        "Define the real decision Argus must make, the hard gates that disqualify whole families, the soft criteria that separate good survivors, and the baseline options the operator would consider without Argus.",
        "Axes rule: create divergence axes that meaningfully partition strategy space. Avoid cosmetic axes that only rename the same mechanism.",
        "Ledger rule: return an initial coverage_ledger whose cells correspond to the most decision-relevant regions of the search space, with explicit uncertainty, hard-gate risk, and evidence strength.",
        "Coverage rule: prefer a compact, high-signal ledger over a combinatorial explosion. Cells should be big enough to matter and small enough to seed distinctly.",
        "Output contract: search_space_frame and coverage_ledger must share one frame_id and give the runtime an auditable starting map for seeding, triage, deepening, and final authoring.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes, especially outcome-backed notes, to remember which cells or hard gates matter in practice, but do not let old runs erase genuinely new regions of the search space."
        )
    return instructions


def _seed_cell_proposals_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: cell-seeding worker for Argus research mode. Seed representative proposals for the selected uncovered or weakly covered cells.",
        "Authoritative evidence, in order: the search_space_frame; the selected ledger cells; the problem spec; reusable learning notes only as priors.",
        "Coverage rule: each proposal must clearly belong to one target cell and embody that cell's hypothesis. Do not collapse multiple cells into one vague average.",
        "Distinctness rule: proposals for different cells must differ in mechanism, dependency shape, or tradeoff profile, not just in wording.",
        "Proposal rule: every ProposalBrief needs a title, summary, seed_rationale, open_questions, evidence, and a candidate with enough mechanism detail to survive evaluation and triage.",
        "Parentage rule: preserve parent_node_ids from the payload when provided so the runtime can audit which earlier nodes or baselines informed the seed.",
        "Output contract: return one coherent ProposalBrief per seeded representative and use batch_summary to explain the strategic spread of the seeded cells.",
    ]
    selected_cells = input_payload.get("target_cells")
    if isinstance(selected_cells, list):
        instructions.append(
            f"Selected-cell count: seed representatives for the {len(selected_cells)} cells in target_cells."
        )
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes to avoid repeating known dead ends in each cell, but do not let prior winners force every cell into the same mechanism."
        )
    return instructions


def _triage_proposals_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: family-level triage judge for Argus research mode. Cull, collapse, or keep proposals based on family merit, not presentation polish.",
        "Authoritative evidence, in order: the search_space_frame; coverage_ledger state; proposal briefs; each proposal's evaluator score and novelty evidence; reusable learning notes only as supporting priors.",
        "Disposition rule: mark survive only when the proposal is decision-relevant and materially stronger than the local alternatives. Mark eliminate for dominated or invalid directions. Mark collapse only when two proposals are substantively the same family and one should absorb the other.",
        "Family rule: triage at the proposal-family level. Avoid keeping two survivors that differ only cosmetically.",
        "Coverage rule: use unexplored_cell_ids to explicitly preserve important uncovered regions rather than letting the runtime forget them.",
        "Rationale rule: every decision rationale must name the decisive mechanism, hard-gate issue, or dominance relation that drove the choice.",
        "Output contract: the survivor_ids must exactly match the proposals marked survive, and next_actions should tell the runtime where to deepen, red-team, or reseed next.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes to recognize recurring failure patterns and outcome-backed risks, but still judge the current proposals on their own evidence."
        )
    return instructions


def _assess_novelty_instructions() -> list[str]:
    return [
        "Role: semantic novelty judge for Argus archive admission.",
        "Authoritative evidence, in order: the candidate thesis and mechanism; archived candidate theses and mechanisms; the problem spec only as context for what counts as a materially distinct approach.",
        "Near-duplicate rule: mark is_novel=false when the candidate keeps the same core mechanism, target value motion, rollout shape, and constraint tradeoff as an archived candidate even if the wording differs.",
        "Trivial rephrasing rule: treat synonym swaps, reordered bullets, or slightly different framing of the same tactic as duplicates.",
        "Shared-vocabulary rule: do not reject a candidate just because it uses similar domain terms. Preserve novelty when the mechanism, adoption motion, monetization logic, or constraint tradeoff is genuinely different.",
        "Nearest-neighbor rule: identify the archive candidate that is substantively closest and report its node id in nearest_neighbor_id whenever one exists.",
        "Similarity rule: use similarity_threshold as the cutoff, but do not apply it mechanically from wording overlap alone. Explain the substantive overlap or difference that justifies the result.",
        "Duplicate signals must be concrete. Name the overlapping mechanism, rollout, dependency, or tradeoff rather than saying the ideas feel similar.",
        "Output contract: novelty_score should rise with meaningful distinctness, max_similarity should reflect the strongest competing overlap in the archive, and summary should clearly say whether this is a near-duplicate, a shared tactic with a different strategic frame, or a genuinely distinct direction.",
    ]


def _assess_novelty_batch_instructions() -> list[str]:
    instructions = _assess_novelty_instructions()
    instructions.extend(
        [
            "Batch mode: assess every candidate in candidates against the same archive snapshot.",
            "Order rule: return one novelty assessment per input candidate in the exact same order as the candidates array.",
            "Do not use other batch candidates as novelty evidence unless they already exist in archive_candidates. Same-batch final dedupe is handled separately by the orchestrator.",
        ]
    )
    return instructions


def _stress_test_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: adversarial stress tester for Argus. Your job is to attack the candidate, not to help it.",
        "Authoritative evidence, in order: explicit problem constraints and success criteria; the candidate mechanism and assumptions; prior score evidence and learning notes only as supporting context.",
        "Adversarial rule: actively look for hidden dependencies, unstated assumptions, operational pain, false comparisons against weak baselines, and real reasons the plan could fail in use.",
        "Ruthlessness rule: prefer concrete kill shots over polite generic critique. If the candidate survives, explain why despite your strongest attacks.",
        "Do not propose a new candidate. Produce a critique that makes later mutate/deepen decisions sharper and more evidence-seeking.",
        "Output contract: hidden_dependencies, kill_shots, and sharp_edges should be specific enough that the operator could falsify or mitigate them.",
    ]
    focus_values = _string_list(input_payload, "stress_test_policy", "focus")
    if focus_values:
        instructions.append(
            "Stress-test focus: " + "; ".join(focus_values) + "."
        )
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes, especially outcome-backed failure patterns, as prompts for where this candidate is likely to break."
        )
    return instructions


def _deepen_candidate_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: deepening worker for Argus. Increase the specificity and execution-readiness of a promising candidate without changing its core mechanism gratuitously.",
        "Authoritative evidence, in order: the candidate itself; prior score and critique evidence; island focus when present; reusable learning notes as supporting priors.",
        "Deepening rule: preserve the candidate's core strategic direction while making the rollout, mechanism, dependencies, and implementation shape more concrete.",
        "Do not flatten the idea into generic detail. Improve the exact places where ambiguity, missing implementation shape, or critique pressure currently weaken the candidate.",
        "If the payload includes critique evidence, address the most material sharp edges directly instead of ignoring them.",
        "Output contract: return one improved candidate with more operational detail, clearer assumptions, and more falsifiable unknowns.",
    ]
    deepen_goal = _nested_string(input_payload, "deepen_policy", "goal")
    if deepen_goal is not None:
        instructions.append(f"Deepening goal: {deepen_goal}")
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes as evidence about which details tend to matter in execution, but do not rewrite the candidate into a different strategy unless the original mechanism collapses."
        )
    return instructions


def _deepen_family_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: deep-dive author for Argus research mode. Turn a surviving proposal into a decision-grade dossier.",
        "Authoritative evidence, in order: the proposal brief; evaluator score and novelty evidence; triage rationale; reusable learning notes only as supporting priors.",
        "Deep-dive rule: preserve the proposal's core mechanism while making the implementation plan, detailed mechanism, assumptions, and key unknowns concrete enough for an operator to act on.",
        "Do not rewrite the proposal into a different strategy. Clarify execution, dependencies, and falsifiable questions instead.",
        "Evidence rule: supporting_evidence must explain why the proposal is viable or what prior observation it builds on. Do not invent external facts.",
        "Output contract: return one DeepDiveDoc that materially upgrades the proposal from a seed brief into an executable plan.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes to stress the execution details that have mattered before, especially outcome-backed constraints and winning patterns."
        )
    return instructions


def _redteam_family_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: adversarial reviewer for Argus research mode. Attack a surviving proposal as if the operator will actually ship it.",
        "Authoritative evidence, in order: the proposal brief; any deep-dive dossier; evaluator score evidence; reusable learning notes only as prior attack surface.",
        "Adversarial rule: surface hidden dependencies, plausible failure modes, and mitigation requirements that could reverse the decision.",
        "Do not help the proposal by inventing excuses. If the review stays positive, make the survival case explicit and bounded.",
        "Verdict rule: verdict should be a short direct judgment of whether the proposal survives current scrutiny, not a generic summary sentence.",
        "Output contract: return one AdversarialReview with concrete risks, mitigations, and confidence grounded in the actual evidence.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: outcome-backed reusable_learning_notes are especially useful here because shipped failures should bias the review toward real-world breakpoints rather than generic critique."
        )
    return instructions


def _mutate_candidate_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: mutation worker for Argus. Repair or redirect a candidate by changing the weakest part of the plan while preserving what still matters.",
        "Authoritative evidence, in order: the candidate; critique evidence; prior score evidence; island context and reusable learning notes as supporting priors.",
        "Mutation rule: respond to the sharpest weakness or critique pressure. Do not produce a cosmetic rewrite of the same fragile plan.",
        "Preserve the causal insight that still works, but change assumptions, rollout shape, or mechanism details enough that the mutation has a real chance of surviving the critique.",
        "If the critique reveals a fatal flaw, pivot around it explicitly instead of pretending the original mechanism is still intact.",
        "Output contract: return a small batch of materially different repair attempts only when the schema asks for a batch; each candidate should explain a distinct repair path rather than paraphrasing one fix.",
    ]
    mutation_goal = _nested_string(input_payload, "mutation_policy", "goal")
    if mutation_goal is not None:
        instructions.append(f"Mutation goal: {mutation_goal}")
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes, especially failure patterns and outcome-backed constraints, to avoid repeating known dead ends during mutation."
        )
    return instructions


def _combine_candidates_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: hybrid synthesis worker for Argus adaptive search. Fuse two candidates only when the hybrid clears an explicit gate, not when it merely sounds broader.",
        "Authoritative evidence, in order: the primary and secondary candidates; any score or critique context; island focus and reusable learning notes only as priors.",
        "Combination rule: keep only the compatible strengths. If the candidates pull in conflicting directions, reject the hybrid instead of producing a kitchen-sink compromise.",
        "Gate rule: every hybrid decision must explicitly name the repaired_failure_mode, complementary_strengths, seam_hypothesis, and complexity_tax before a hybrid can survive.",
        "Candidate rule: only include candidate when verdict is pursue. If the seam is vague or the complexity tax outweighs the upside, return hold or reject with candidate set to null.",
        "Do not average two candidates into vague compromise language. A pursued hybrid must still be distinctive, evaluable, and operationally concrete.",
        "Output contract: return one or more gated hybrid decisions. Each pursued decision must represent a materially different integration seam rather than a paraphrase set.",
    ]
    combine_goal = _nested_string(input_payload, "combine_policy", "goal")
    if combine_goal is not None:
        instructions.append(f"Combination goal: {combine_goal}")
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes as evidence about which combinations tend to work or fail, especially when prior runs exposed brittle seams or hidden dependencies."
        )
    return instructions


def _assess_hybrid_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: hybrid-gating judge for Argus research mode. Evaluate whether combining survivors creates a justified new seam or just complexity theater.",
        "Authoritative evidence, in order: the source proposals; their deep dives and adversarial reviews; the search-space frame; reusable learning notes only as supporting priors.",
        "Seam rule: do not approve a hybrid unless you can name the seam_hypothesis, the repaired_failure_mode, and the complementary strengths that make the combination better than either source alone.",
        "Complexity-tax rule: complexity_tax must be explicit and serious. If the seam is vague or the complexity tax overwhelms the expected upside, reject or hold the hybrid.",
        "Anti-kitchen-sink rule: combining two strong proposals is not enough. The hybrid must repair a real failure mode or unlock a new defensible upside.",
        "Output contract: choose pursue, hold, or reject and make the summary decisive about why the hybrid does or does not clear the bar.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes to remember brittle seams or successful integrations from prior runs, but keep the verdict grounded in the current proposal pair."
        )
    return instructions


def _compress_learning_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: learning compression worker for Argus. Distill the current search state into reusable lessons that later runs can actually benefit from.",
        "Authoritative evidence, in order: archived nodes, pruned nodes, existing learning notes, island context, and reusable learning notes only as prior memory.",
        "Compression rule: extract patterns, failure modes, constraints, and routing hints that are reusable beyond one exact candidate. Do not merely restate the winning thesis.",
        "Specificity rule: each note should say what pattern was observed and why it mattered. Avoid bland advice like 'be more specific' or 'consider tradeoffs'.",
        "Balance rule: include both winning and losing lessons when they are genuinely reusable. Preserve the strongest constraints and repeated failure shapes, not just positive takeaways.",
        "Output contract: honor max_notes, keep note types appropriate, and ensure source_node_ids point to the concrete nodes that generated the lesson.",
    ]
    max_notes = input_payload.get("max_notes")
    if isinstance(max_notes, int):
        instructions.append(f"Note budget: return at most {max_notes} compressed learning notes.")
    compression_goal = _nested_string(input_payload, "compression_policy", "goal")
    if compression_goal is not None:
        instructions.append(f"Compression goal: {compression_goal}")
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: compare the current run against reusable_learning_notes so you preserve genuinely new lessons and reinforce recurring patterns with clearer wording."
        )
    return instructions


def _pairwise_rank_instructions(input_payload: Mapping[str, JSONValue]) -> list[str]:
    objective_name = _nested_string(input_payload, "objective", "name")
    objective_description = _nested_string(input_payload, "objective", "description")
    instructions = [
        "Role: pairwise ranking judge for Argus finalist selection.",
        "Authoritative evidence, in order: the stated objective; explicit problem constraints and success criteria; each candidate's mechanism and failure modes; each node's score evidence, novelty score, and critique evidence when present.",
        "Decision rule: choose exactly one winner, left or right. There are no ties. Pick the candidate that better satisfies the stated objective for the actual problem, not the one that merely sounds sharper.",
        "Hard-constraint rule: do not choose a candidate whose plan fails explicit constraints or depends on unrealistic assumptions unless the other candidate is even less viable under the same problem.",
        "Adversarial checks: compare hidden dependencies, operational pain, weak baseline comparisons, implementation fragility, and whether apparent upside is actually supported by the mechanism and evidence.",
        "Anti-style rule: do not reward phrasing polish, generic ambition, or buzzwords. Reward decisive substance and realistic tradeoffs.",
        "Use decisive_advantages and decisive_risks to name the actual tradeoffs that drove the result rather than restating both candidates.",
        "Set confidence based on the clarity of the tradeoff and the quality of the evidence. Lower it when the choice depends on unresolved assumptions.",
    ]
    if objective_name is not None:
        instructions.append(
            f"Objective-specific focus for {objective_name}: {_objective_focus(objective_name)}"
        )
    if objective_description is not None:
        instructions.append(
            "Objective description is authoritative. Use it to break close calls when the generic ranking heuristics conflict."
        )
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: when reusable_learning_notes are present, use them as prior evidence about patterns that succeeded or failed before. Notes tagged with evidence_sources containing outcome_feedback reflect shipped outcomes and should carry more weight than search-only learnings, but keep the winner grounded in the current problem and objective."
        )
    return instructions


def _write_final_decision_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: final decision author for Argus research mode. Read the full artifact bundle and write the decision package the operator can act on.",
        "Authoritative evidence, in order: the search_space_frame; current coverage_ledger; proposal briefs; triage report; deep dives; adversarial reviews; hybrid assessments; the problem spec and reusable learning notes only as supporting context.",
        "Decision rule: choose the proposal that best satisfies the target decision under the hard gates and soft criteria. Do not default to the most eloquent or most ambitious option.",
        "Comparison rule: produce a comparison_matrix whose criteria match the real decision and whose rows explain the decisive advantages and liabilities for each finalist.",
        "Portfolio rule: selected_proposal_id, conservative_proposal_id, and high_upside_proposal_id should differ when the evidence supports genuinely different bets. Do not force artificial differentiation if one proposal legitimately fills more than one role.",
        "Rejection rule: rejected_proposal_ids should include notable losers that still taught the system something, not every proposal that failed triage.",
        "Execution rule: first_spike, kill_criteria, next_experiments, mitigations, and reversal_conditions must be concrete enough to guide an actual implementation decision.",
        "Authoring rule: write both decision_summary_markdown and decision_report_markdown from the current artifact bundle. The summary should be concise and decision-grade; the report should read like an operator memo with explicit best-bet logic, tradeoffs, runner-up conditions, risks, and immediate next steps.",
        "Grounding rule: every claim in the markdown outputs should trace back to the supplied artifacts. Do not invent evidence, hidden research, or stakeholder preferences that are not in the bundle.",
        "Output contract: return comparison_matrix, final_decision_doc, decision_summary_markdown, and decision_report_markdown, and keep all proposal references consistent with the supplied artifact ids.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes, especially outcome-backed notes, to sharpen the decision rule and risk framing, but never let them override the current artifact evidence."
        )
    return instructions


def _judge_benchmark_modes_instructions(
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        "Role: benchmark comparison judge for Argus runtime modes.",
        "Authoritative evidence, in order: the benchmark problem spec; benchmark_case evaluation_notes and expected_qualities; each mode output's final_recommendation, selected_theses, summary_markdown, and optional research_final_decision artifact.",
        "Primary question: which runtime output would a serious team act on next if they had to pick one artifact package from this benchmark case?",
        "Judge decision_quality based on whether the output sharpens the real decision, preserves meaningful alternatives, and explains why the winner beats the runner-up.",
        "Judge actionability based on whether the first spike or next experiments are concrete, discriminating, and immediately useful to the operator.",
        "Judge tradeoff_clarity based on whether assumptions, explicit tradeoffs, reversal conditions, and reasons-to-be-wrong are visible rather than implied.",
        "Judge risk_quality based on whether the output names real failure modes and mitigations rather than generic caution language.",
        "Judge experiment_quality based on whether the proposed next move can actually falsify or advance the decision.",
        "Anti-style rule: do not reward longer prose, nicer formatting, or generic confidence by itself. Reward decision-grade substance.",
        "Adversarial rule: penalize polished but vague summaries, weak runner-up logic, and non-specific experiments.",
        "Output contract: return one BenchmarkModeJudgment per mode in the exact input order, pick exactly one winner and one runner-up, and use decisive_reasons plus per-mode evidence to cite the concrete artifacts that drove the choice.",
    ]
    mode_outputs = input_payload.get("mode_outputs")
    if isinstance(mode_outputs, list):
        instructions.append(
            f"Comparison scope: evaluate all {len(mode_outputs)} runtime modes in mode_outputs."
        )
    benchmark_case = input_payload.get("benchmark_case")
    if isinstance(benchmark_case, Mapping):
        case_id = benchmark_case.get("case_id")
        family = benchmark_case.get("family")
        if isinstance(case_id, str) and isinstance(family, str):
            instructions.append(f"Benchmark target: case_id={case_id}, family={family}.")
    return instructions


def _migrate_candidate_instructions() -> list[str]:
    return [
        "Role: cross-island migration worker for Argus.",
        "Goal: carry the strongest causal insight from the source candidate into the destination island's optimization bias without copying the source candidate verbatim.",
        "Preserve what actually matters from the source mechanism, but rewrite the candidate so it genuinely fits the destination island's generation_focus and tradeoff profile.",
        "Do not paraphrase the source candidate. Return a materially new candidate with a distinct thesis, mechanism framing, or rollout shape.",
        "Keep the result concrete, auditable, and viable enough to survive downstream novelty and evaluation checks.",
        "If the source idea does not transfer cleanly, adapt only the portable insight instead of dragging over the whole plan.",
        "Output one candidate, not a batch, and keep assumptions, failure modes, unknowns, and implementation shape explicit.",
    ]


def _default_action_instructions(
    action_name: str,
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    instructions = [
        f"Role: execute the Argus action `{action_name}` faithfully using only the supplied problem spec and input payload.",
        "Prefer concrete mechanisms, explicit tradeoffs, and realistic assumptions over generic brainstorming language.",
        "If the schema requires judgment, make that judgment explicit in the JSON fields instead of relying on free-form prose.",
    ]
    if _has_reusable_learning_notes(input_payload):
        instructions.append(
            "Reusable priors: use reusable_learning_notes as compact prior art from earlier Argus runs. If a note is tagged with evidence_sources containing outcome_feedback, treat it as stronger observed evidence from shipped experiments. Apply all priors as guardrails and pattern memory, but do not cargo-cult them when the current problem points elsewhere."
        )
    return instructions


def _objective_focus(objective_name: str) -> str:
    normalized = objective_name.strip().lower()
    if normalized == "best_overall":
        return (
            "Balance usefulness, specificity, plausibility, implementation tractability, "
            "upside, and adversarial robustness without letting one flashy advantage hide "
            "a weak mechanism."
        )
    if normalized == "conservative_option":
        return (
            "Prefer operational clarity, tractability, plausibility, robustness, and "
            "confidence over raw upside. The safer winner should still meaningfully solve "
            "the problem."
        )
    if normalized == "high_upside_option":
        return (
            "Reward justified upside, distinctiveness, and strategic leverage, but reject "
            "fantasy plans that collapse under execution risk or unrealistic dependencies."
        )
    return (
        "Apply the stated objective literally and make the decisive tradeoff explicit in the "
        "summary."
    )


def _nested_string(
    payload: Mapping[str, JSONValue],
    parent_key: str,
    child_key: str,
) -> str | None:
    parent = payload.get(parent_key)
    if not isinstance(parent, Mapping):
        return None
    value = parent.get(child_key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _string_list(
    payload: Mapping[str, JSONValue],
    parent_key: str,
    child_key: str,
) -> list[str]:
    parent = payload.get(parent_key)
    if not isinstance(parent, Mapping):
        return []
    value = parent.get(child_key)
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            results.append(normalized)
    return results


def _format_instruction_lines(lines: list[str]) -> list[str]:
    return [f"{index}. {line}" for index, line in enumerate(lines, start=1)]


def _has_reusable_learning_notes(input_payload: Mapping[str, JSONValue]) -> bool:
    value = input_payload.get("reusable_learning_notes")
    return isinstance(value, list) and len(value) > 0
