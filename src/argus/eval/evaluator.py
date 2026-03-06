from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
import re

from argus.errors import ArgusValidationError
from argus.models import Candidate, Node, ProblemSpec, ScoreVector

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "this",
    "those",
    "to",
    "up",
    "with",
    "will",
    "would",
    "must",
    "should",
    "could",
    "can",
    "needs",
    "need",
    "using",
    "use",
    "used",
    "only",
    "keep",
    "stay",
    "against",
    "before",
    "after",
    "through",
    "while",
    "under",
    "over",
    "not",
    "without",
    "avoid",
    "thesis",
    "mechanism",
    "assumptions",
    "strengths",
    "failure",
    "modes",
    "unknowns",
    "evidence",
    "implementation",
    "shape",
}

_NEGATIVE_CONSTRAINT_MARKERS = (
    "no ",
    "without ",
    "avoid ",
    "do not ",
    "don't ",
    "must not ",
    "cannot ",
    "can't ",
    "never ",
)

_INCREMENTAL_TERMS = {
    "pilot",
    "phased",
    "phase",
    "prototype",
    "rollout",
    "experiment",
    "service",
    "workflow",
    "instrument",
    "incremental",
    "persist",
    "score",
    "measure",
    "ship",
}

_EXPANSIVE_TERMS = {
    "rewrite",
    "marketplace",
    "ecosystem",
    "platform",
    "allinone",
    "category",
    "moonshot",
    "boil",
    "ocean",
}

_UPSIDE_TERMS = {
    "moat",
    "retention",
    "compound",
    "automation",
    "defensible",
    "lock",
    "workflow",
    "network",
    "expand",
    "upsell",
    "monetize",
    "leverage",
    "10x",
    "durable",
}

_HYPE_TERMS = {
    "revolutionary",
    "magic",
    "frictionless",
    "viral",
    "disruptive",
    "instant",
    "breakthrough",
}


@dataclass(frozen=True, slots=True)
class EvaluatorWeights:
    distinctiveness: float = 0.8
    usefulness: float = 1.35
    specificity: float = 1.0
    plausibility: float = 1.25
    implementation_tractability: float = 1.15
    upside: float = 1.1
    adversarial_robustness: float = 0.85
    evidence_quality: float = 0.5

    def __post_init__(self) -> None:
        for field_name in (
            "distinctiveness",
            "usefulness",
            "specificity",
            "plausibility",
            "implementation_tractability",
            "upside",
            "adversarial_robustness",
            "evidence_quality",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
                raise ArgusValidationError(
                    f"{field_name} must be a positive finite number, got {value!r}."
                )

    @property
    def total_weight(self) -> float:
        return (
            self.distinctiveness
            + self.usefulness
            + self.specificity
            + self.plausibility
            + self.implementation_tractability
            + self.upside
            + self.adversarial_robustness
            + self.evidence_quality
        )


DEFAULT_EVALUATOR_WEIGHTS = EvaluatorWeights()


class DeterministicEvaluator:
    """Score candidates with explicit heuristics and fixed weights."""

    def __init__(self, *, weights: EvaluatorWeights = DEFAULT_EVALUATOR_WEIGHTS) -> None:
        self._weights = weights

    @property
    def weights(self) -> EvaluatorWeights:
        return self._weights

    def evaluate(
        self,
        problem_spec: ProblemSpec,
        candidate: Candidate,
        *,
        novelty_score: float | None = None,
    ) -> ScoreVector:
        if novelty_score is not None:
            novelty_component = _normalize_probability(novelty_score, "novelty_score")
        else:
            novelty_component = None

        candidate_text = candidate.text_projection()
        candidate_token_list = _content_token_list(candidate_text)
        candidate_tokens = _content_tokens(candidate_text)
        commitment_tokens = _content_tokens(_candidate_commitment_text(candidate))
        problem_tokens = _problem_tokens(problem_spec)
        evidence_tokens = _content_tokens(" ".join(candidate.evidence))

        hard_constraint_reasons = _hard_constraint_reasons(
            problem_spec=problem_spec,
            candidate=candidate,
            candidate_tokens=candidate_tokens,
            commitment_tokens=commitment_tokens,
            problem_tokens=problem_tokens,
        )
        hard_constraint_pass = not hard_constraint_reasons

        lexical_diversity = _ratio(len(set(candidate_token_list)), max(len(candidate_token_list), 1))
        section_completeness = _average(
            _presence_score(candidate.assumptions),
            _presence_score(candidate.strengths),
            _presence_score(candidate.failure_modes),
            _presence_score(candidate.unknowns),
            1.0 if candidate.implementation_shape else 0.0,
            _presence_score(candidate.evidence),
        )
        detail_density = _average(
            _saturating_count(len(_content_token_list(candidate.thesis)), 8),
            _saturating_count(len(_content_token_list(candidate.mechanism)), 12),
            _saturating_count(
                sum(len(_content_token_list(value)) for value in candidate.assumptions),
                18,
            ),
            _saturating_count(
                sum(len(_content_token_list(value)) for value in candidate.failure_modes),
                18,
            ),
        )
        problem_overlap = _overlap_ratio(problem_tokens, candidate_tokens)
        evidence_count_score = _saturating_count(len(candidate.evidence), 3)
        evidence_detail_score = _saturating_count(
            sum(len(_content_token_list(value)) for value in candidate.evidence),
            18,
        )
        evidence_overlap = _overlap_ratio(problem_tokens, evidence_tokens)
        mechanism_detail = _average(
            _saturating_count(len(_content_token_list(candidate.mechanism)), 14),
            1.0 if candidate.implementation_shape else 0.35,
        )
        strengths_score = _saturating_count(len(candidate.strengths), 3)
        risk_articulation = _average(
            _saturating_count(len(candidate.failure_modes), 3),
            _saturating_count(len(candidate.unknowns), 3),
        )
        novelty_basis = lexical_diversity if novelty_component is None else novelty_component
        support_balance = 1.0 - _clamp(
            (
                len(candidate.assumptions)
                + len(candidate.unknowns)
                - len(candidate.strengths)
                - len(candidate.evidence)
            )
            / 6.0
        )
        hype_penalty = _saturating_count(_keyword_hits(candidate_text, _HYPE_TERMS), 2)
        incremental_signal = _saturating_count(
            _keyword_hits(candidate_text, _INCREMENTAL_TERMS),
            4,
        )
        expansive_penalty = _saturating_count(
            _keyword_hits(candidate_text, _EXPANSIVE_TERMS),
            3,
        )
        leverage_signal = _saturating_count(_keyword_hits(candidate_text, _UPSIDE_TERMS), 4)

        distinctiveness = _rounded_score(
            0.45 * novelty_basis + 0.35 * lexical_diversity + 0.20 * section_completeness
        )
        usefulness = _rounded_score(
            0.50 * problem_overlap + 0.30 * mechanism_detail + 0.20 * strengths_score
        )
        specificity = _rounded_score(
            0.45 * section_completeness + 0.35 * detail_density + 0.20 * evidence_count_score
        )
        plausibility = _rounded_score(
            0.40 * mechanism_detail
            + 0.30 * _average(strengths_score, evidence_count_score, evidence_overlap)
            + 0.20 * support_balance
            + 0.10 * (1.0 - hype_penalty)
        )
        implementation_tractability = _rounded_score(
            0.40 * (1.0 if candidate.implementation_shape else 0.25)
            + 0.25 * mechanism_detail
            + 0.25 * incremental_signal
            + 0.10 * support_balance
            - 0.15 * expansive_penalty
        )
        upside = _rounded_score(
            0.40 * strengths_score + 0.35 * leverage_signal + 0.25 * novelty_basis
        )
        adversarial_robustness = _rounded_score(
            0.50 * risk_articulation + 0.25 * problem_overlap + 0.25 * evidence_count_score
        )
        evidence_quality = _rounded_score(
            0.55 * evidence_count_score
            + 0.25 * evidence_detail_score
            + 0.20 * evidence_overlap
        )

        total_score = 0.0
        if hard_constraint_pass:
            total_score = _rounded_total(
                distinctiveness * self._weights.distinctiveness
                + usefulness * self._weights.usefulness
                + specificity * self._weights.specificity
                + plausibility * self._weights.plausibility
                + implementation_tractability * self._weights.implementation_tractability
                + upside * self._weights.upside
                + adversarial_robustness * self._weights.adversarial_robustness
                + evidence_quality * self._weights.evidence_quality
            )

        confidence_estimate = _rounded_score(
            0.25 * specificity
            + 0.25 * plausibility
            + 0.20 * adversarial_robustness
            + 0.15 * evidence_quality
            + 0.15 * (1.0 if hard_constraint_pass else 0.2)
        )
        if novelty_component is not None:
            confidence_estimate = _rounded_score(
                confidence_estimate * (0.85 + (0.15 * novelty_component))
            )
        if not hard_constraint_pass:
            confidence_estimate = min(confidence_estimate, 0.45)

        return ScoreVector(
            hard_constraint_pass=hard_constraint_pass,
            hard_constraint_reasons=hard_constraint_reasons,
            distinctiveness=distinctiveness,
            usefulness=usefulness,
            specificity=specificity,
            plausibility=plausibility,
            implementation_tractability=implementation_tractability,
            upside=upside,
            adversarial_robustness=adversarial_robustness,
            evidence_quality=evidence_quality,
            total_score=total_score,
            confidence_estimate=confidence_estimate,
        )


def rank_nodes(nodes: Iterable[Node]) -> list[Node]:
    """Sort scored nodes for expansion or winner selection."""

    return sorted(nodes, key=_rank_key, reverse=True)


def _rank_key(node: Node) -> tuple[float, ...]:
    score = node.score
    if score is None:
        raise ArgusValidationError(f"Node {node.node_id!r} has no score to rank.")
    return (
        1.0 if score.hard_constraint_pass else 0.0,
        score.total_score,
        score.confidence_estimate,
        score.usefulness,
        score.plausibility,
        node.novelty_score,
        score.adversarial_robustness,
    )


def _candidate_commitment_text(candidate: Candidate) -> str:
    sections = [candidate.thesis, candidate.mechanism]
    sections.extend(candidate.strengths)
    if candidate.implementation_shape:
        sections.append(candidate.implementation_shape)
    return "\n".join(sections)


def _hard_constraint_reasons(
    *,
    problem_spec: ProblemSpec,
    candidate: Candidate,
    candidate_tokens: set[str],
    commitment_tokens: set[str],
    problem_tokens: set[str],
) -> list[str]:
    reasons: list[str] = []

    overlap_count = len(problem_tokens & candidate_tokens)
    if problem_tokens:
        coverage_ratio = overlap_count / len(problem_tokens)
        if overlap_count < 2 and coverage_ratio < 0.1:
            reasons.append(
                "Candidate does not engage the stated constraints or success criteria."
            )

    if len(_content_token_list(candidate.mechanism)) < 5:
        reasons.append("Candidate mechanism is too underspecified for evaluation.")

    if not candidate.failure_modes and not candidate.unknowns:
        reasons.append(
            "Candidate does not surface failure modes or unknowns for adversarial review."
        )

    commitment_text = _normalize_space(_candidate_commitment_text(candidate))
    for constraint in problem_spec.constraints:
        normalized_constraint = _normalize_space(constraint)
        if not _contains_negative_marker(normalized_constraint):
            continue
        if _contains_negative_marker(commitment_text):
            continue
        constraint_tokens = _content_tokens(constraint)
        if not constraint_tokens:
            continue
        overlap = len(constraint_tokens & commitment_tokens)
        threshold = max(1, math.ceil(len(constraint_tokens) * 0.6))
        if overlap >= threshold:
            reasons.append(f"Candidate appears to violate constraint: {constraint.strip()}")

    return reasons


def _problem_tokens(problem_spec: ProblemSpec) -> set[str]:
    parts = [problem_spec.request, *problem_spec.constraints, *problem_spec.success_criteria]
    return _content_tokens(" ".join(parts))


def _content_tokens(text: str) -> set[str]:
    return set(_content_token_list(text))


def _content_token_list(text: str) -> list[str]:
    return [
        token for token in _tokenize(text) if len(token) > 2 and token not in _STOPWORDS
    ]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _normalize_space(text: str) -> str:
    return " ".join(text.lower().split())


def _contains_negative_marker(text: str) -> bool:
    return any(marker in text for marker in _NEGATIVE_CONSTRAINT_MARKERS)


def _keyword_hits(text: str, keywords: set[str]) -> int:
    tokens = set(_tokenize(text))
    return sum(1 for keyword in keywords if keyword in tokens)


def _presence_score(values: list[str]) -> float:
    return 1.0 if values else 0.0


def _overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def _saturating_count(value: int, full_score_at: int) -> float:
    if full_score_at <= 0:
        raise ArgusValidationError("full_score_at must be positive.")
    return _clamp(value / full_score_at)


def _average(*values: float) -> float:
    if not values:
        raise ArgusValidationError("average requires at least one value.")
    return sum(values) / len(values)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _rounded_score(value: float) -> float:
    return round(_clamp(value), 4)


def _rounded_total(value: float) -> float:
    return round(max(value, 0.0), 4)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return min(max(value, lower), upper)


def _normalize_probability(value: float, field_name: str) -> float:
    if not isinstance(value, int | float) or not math.isfinite(value):
        raise ArgusValidationError(
            f"{field_name} must be a finite number, got {value!r}."
        )
    if value < 0 or value > 1:
        raise ArgusValidationError(
            f"{field_name} must be between 0 and 1 inclusive, got {value!r}."
        )
    return float(value)
