from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from argus.errors import ArgusValidationError
from argus.models import Candidate, JSONValue, Node, ProblemSpec, ScoreVector
from argus.providers import Provider, StructuredOutputSchema


@dataclass(frozen=True, slots=True)
class EvaluationAssessment:
    score: ScoreVector
    summary: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.score, ScoreVector):
            raise ArgusValidationError(
                "score must be a ScoreVector instance, "
                f"got {type(self.score).__name__}."
            )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(self, "strengths", _normalize_string_list(self.strengths, "strengths"))
        object.__setattr__(self, "weaknesses", _normalize_string_list(self.weaknesses, "weaknesses"))
        object.__setattr__(
            self,
            "open_questions",
            _normalize_string_list(self.open_questions, "open_questions"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score.to_dict(),
            "summary": self.summary,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "open_questions": list(self.open_questions),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "EvaluationAssessment":
        data = _validate_payload_keys(
            payload,
            field_name="EvaluationAssessment",
            required={"score", "summary", "strengths", "weaknesses", "open_questions"},
        )
        return cls(
            score=ScoreVector.from_dict(data["score"]),
            summary=data["summary"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            open_questions=data["open_questions"],
        )


@dataclass(frozen=True, slots=True)
class PairwiseRankingAssessment:
    winner: str
    summary: str
    decisive_advantages: list[str] = field(default_factory=list)
    decisive_risks: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.winner not in {"left", "right"}:
            raise ArgusValidationError(
                "winner must be either 'left' or 'right', "
                f"got {self.winner!r}."
            )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(
            self,
            "decisive_advantages",
            _normalize_string_list(self.decisive_advantages, "decisive_advantages"),
        )
        object.__setattr__(
            self,
            "decisive_risks",
            _normalize_string_list(self.decisive_risks, "decisive_risks"),
        )
        object.__setattr__(
            self,
            "confidence",
            _normalize_probability(self.confidence, "confidence"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "winner": self.winner,
            "summary": self.summary,
            "decisive_advantages": list(self.decisive_advantages),
            "decisive_risks": list(self.decisive_risks),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "PairwiseRankingAssessment":
        data = _validate_payload_keys(
            payload,
            field_name="PairwiseRankingAssessment",
            required={
                "winner",
                "summary",
                "decisive_advantages",
                "decisive_risks",
                "confidence",
            },
        )
        return cls(
            winner=data["winner"],
            summary=data["summary"],
            decisive_advantages=data["decisive_advantages"],
            decisive_risks=data["decisive_risks"],
            confidence=data["confidence"],
        )


class AgenticEvaluator:
    """Evaluate candidates via the provider layer using a structured rubric."""

    def __init__(self, *, provider: Provider) -> None:
        self._provider = provider

    @property
    def provider(self) -> Provider:
        return self._provider

    def evaluate(
        self,
        problem_spec: ProblemSpec,
        candidate: Candidate,
        *,
        novelty_score: float | None = None,
    ) -> EvaluationAssessment:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        if not isinstance(candidate, Candidate):
            raise ArgusValidationError(
                "candidate must be a Candidate instance, "
                f"got {type(candidate).__name__}."
            )

        input_payload: dict[str, JSONValue] = {
            "candidate": candidate.to_dict(),
            "rubric": {
                "dimensions": [
                    "distinctiveness",
                    "usefulness",
                    "specificity",
                    "plausibility",
                    "implementation_tractability",
                    "upside",
                    "adversarial_robustness",
                    "evidence_quality",
                ],
                "hard_constraint_policy": (
                    "Set hard_constraint_pass=false if the candidate violates explicit constraints, "
                    "fails to address the stated problem, or ignores required tradeoffs."
                ),
                "scoring_scale": "Each score dimension except total_score and hard_constraint_reasons must be between 0 and 1 inclusive.",
                "quality_bar": (
                    "Judge substance over wording. Do not reward buzzwords, generic optimism, "
                    "or format compliance by itself."
                ),
            },
        }
        if novelty_score is not None:
            input_payload["novelty_score"] = _normalize_probability(
                novelty_score,
                "novelty_score",
            )

        response = self._provider.run_action(
            action_name="evaluate_candidate",
            problem_spec=problem_spec,
            input_payload=input_payload,
            output_schema=evaluation_assessment_schema(),
        )
        return response.payload

    def compare_nodes(
        self,
        problem_spec: ProblemSpec,
        left: Node,
        right: Node,
        *,
        objective: str,
        objective_description: str,
    ) -> PairwiseRankingAssessment:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        if not isinstance(left, Node):
            raise ArgusValidationError(
                f"left must be a Node instance, got {type(left).__name__}."
            )
        if not isinstance(right, Node):
            raise ArgusValidationError(
                f"right must be a Node instance, got {type(right).__name__}."
            )
        if left.node_id == right.node_id:
            raise ArgusValidationError("left and right must be different nodes.")
        if left.score is None:
            raise ArgusValidationError(f"Node {left.node_id!r} has no score to compare.")
        if right.score is None:
            raise ArgusValidationError(f"Node {right.node_id!r} has no score to compare.")

        normalized_objective = _normalize_non_empty_string(objective, "objective")
        normalized_description = _normalize_non_empty_string(
            objective_description,
            "objective_description",
        )
        response = self._provider.run_action(
            action_name="rank",
            problem_spec=problem_spec,
            input_payload={
                "objective": {
                    "name": normalized_objective,
                    "description": normalized_description,
                },
                "left": _comparison_node_payload(left),
                "right": _comparison_node_payload(right),
                "comparison_policy": {
                    "decision_rule": (
                        "Choose the candidate that better satisfies the stated objective based "
                        "on mechanism quality, score evidence, critique evidence, and realism."
                    ),
                    "anti_style_rule": (
                        "Do not reward phrasing polish, buzzwords, or generic optimism unless "
                        "they reflect a materially stronger plan."
                    ),
                },
            },
            output_schema=pairwise_ranking_assessment_schema(),
        )
        return response.payload


def rank_nodes(nodes: Iterable[Node]) -> list[Node]:
    """Sort scored nodes for expansion or winner selection."""

    return sorted(nodes, key=_rank_key, reverse=True)


def evaluation_assessment_schema() -> StructuredOutputSchema[EvaluationAssessment]:
    return StructuredOutputSchema(
        name="evaluation_assessment",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["score", "summary", "strengths", "weaknesses", "open_questions"],
            "properties": {
                "score": _score_vector_json_schema(),
                "summary": {"type": "string", "minLength": 1},
                "strengths": _string_array_schema(),
                "weaknesses": _string_array_schema(),
                "open_questions": _string_array_schema(),
            },
        },
        validator=EvaluationAssessment.from_dict,
    )


def pairwise_ranking_assessment_schema() -> StructuredOutputSchema[PairwiseRankingAssessment]:
    probability_field = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    return StructuredOutputSchema(
        name="pairwise_ranking_assessment",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "winner",
                "summary",
                "decisive_advantages",
                "decisive_risks",
                "confidence",
            ],
            "properties": {
                "winner": {
                    "type": "string",
                    "enum": ["left", "right"],
                },
                "summary": {"type": "string", "minLength": 1},
                "decisive_advantages": _string_array_schema(),
                "decisive_risks": _string_array_schema(),
                "confidence": probability_field,
            },
        },
        validator=PairwiseRankingAssessment.from_dict,
    )


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


def _score_vector_json_schema() -> dict[str, JSONValue]:
    probability_field = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "hard_constraint_pass",
            "hard_constraint_reasons",
            "distinctiveness",
            "usefulness",
            "specificity",
            "plausibility",
            "implementation_tractability",
            "upside",
            "adversarial_robustness",
            "evidence_quality",
            "total_score",
            "confidence_estimate",
        ],
        "properties": {
            "hard_constraint_pass": {"type": "boolean"},
            "hard_constraint_reasons": _string_array_schema(),
            "distinctiveness": probability_field,
            "usefulness": probability_field,
            "specificity": probability_field,
            "plausibility": probability_field,
            "implementation_tractability": probability_field,
            "upside": probability_field,
            "adversarial_robustness": probability_field,
            "evidence_quality": probability_field,
            "total_score": {"type": "number", "minimum": 0.0},
            "confidence_estimate": probability_field,
        },
    }


def _string_array_schema() -> dict[str, JSONValue]:
    return {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
    }


def _comparison_node_payload(node: Node) -> dict[str, JSONValue]:
    if node.score is None:
        raise ArgusValidationError(f"Node {node.node_id!r} has no score to compare.")
    payload: dict[str, JSONValue] = {
        "node_id": node.node_id,
        "candidate": node.candidate.to_dict(),
        "score": node.score.to_dict(),
        "novelty_score": node.novelty_score,
    }
    if node.critique is not None:
        payload["critique"] = node.critique.to_dict()
    return payload


def _normalize_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _normalize_string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ArgusValidationError(
            f"{field_name} must be a list of strings, got {type(value).__name__}."
        )
    normalized: list[str] = []
    for index, entry in enumerate(value):
        normalized.append(_normalize_non_empty_string(entry, f"{field_name}[{index}]"))
    return normalized


def _normalize_probability(value: object, field_name: str) -> float:
    if not isinstance(value, int | float):
        raise ArgusValidationError(
            f"{field_name} must be a finite number, got {type(value).__name__}."
        )
    normalized = float(value)
    if normalized < 0.0 or normalized > 1.0:
        raise ArgusValidationError(
            f"{field_name} must be between 0 and 1 inclusive, got {normalized!r}."
        )
    return normalized


def _validate_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ArgusValidationError(
            f"{field_name} payload must be a dict, got {type(payload).__name__}."
        )

    keys = set(payload)
    missing = required - keys
    unexpected = keys - required
    if missing:
        joined = ", ".join(sorted(missing))
        raise ArgusValidationError(f"{field_name} payload is missing required keys: {joined}.")
    if unexpected:
        joined = ", ".join(sorted(str(key) for key in unexpected))
        raise ArgusValidationError(f"{field_name} payload contains unexpected keys: {joined}.")
    return dict(payload)
