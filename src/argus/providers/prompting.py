from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from argus.models import JSONValue, ProblemSpec
from argus.providers.base import StructuredOutputSchema


def render_codex_prompt(
    *,
    action_name: str,
    problem_spec: ProblemSpec,
    input_payload: Mapping[str, JSONValue],
    output_schema: StructuredOutputSchema[Any],
) -> str:
    sections = [
        "# Argus Codex Worker",
        "You are the Codex worker behind the Argus provider layer.",
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


def _action_specific_instructions(
    action_name: str,
    input_payload: Mapping[str, JSONValue],
) -> list[str]:
    normalized_action = action_name.strip().lower()
    if normalized_action == "evaluate_candidate":
        return _evaluate_candidate_instructions(input_payload)
    if normalized_action == "assess_novelty":
        return _assess_novelty_instructions()
    if normalized_action == "rank":
        return _pairwise_rank_instructions(input_payload)
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
            "Reusable priors: when reusable_learning_notes are present, treat them as archived observations about past winning patterns, failure modes, and constraints. Use them to pressure-test the candidate, but never let them override the current problem spec."
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
            "Reusable priors: when reusable_learning_notes are present, use them as prior evidence about patterns that succeeded or failed before, but keep the winner grounded in the current problem and objective."
        )
    return instructions


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
            "Reusable priors: use reusable_learning_notes as compact prior art from earlier Argus runs. Apply them as guardrails and pattern memory, but do not cargo-cult them when the current problem points elsewhere."
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


def _format_instruction_lines(lines: list[str]) -> list[str]:
    return [f"{index}. {line}" for index, line in enumerate(lines, start=1)]


def _has_reusable_learning_notes(input_payload: Mapping[str, JSONValue]) -> bool:
    value = input_payload.get("reusable_learning_notes")
    return isinstance(value, list) and len(value) > 0
