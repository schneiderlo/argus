from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from argus.errors import ArgusValidationError
from argus.models import Candidate, JSONValue, Node, ProblemSpec
from argus.providers import Provider, StructuredOutputSchema


@dataclass(frozen=True, slots=True)
class NoveltyAssessment:
    novelty_score: float
    max_similarity: float
    nearest_neighbor_id: str | None
    similarity_threshold: float
    is_novel: bool
    summary: str
    duplicate_signals: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "novelty_score",
            _normalize_probability(self.novelty_score, "novelty_score"),
        )
        object.__setattr__(
            self,
            "max_similarity",
            _normalize_probability(self.max_similarity, "max_similarity"),
        )
        object.__setattr__(
            self,
            "similarity_threshold",
            _normalize_probability(self.similarity_threshold, "similarity_threshold"),
        )
        if self.nearest_neighbor_id is not None:
            object.__setattr__(
                self,
                "nearest_neighbor_id",
                _normalize_non_empty_string(self.nearest_neighbor_id, "nearest_neighbor_id"),
            )
        if not isinstance(self.is_novel, bool):
            raise ArgusValidationError(
                f"is_novel must be a boolean, got {type(self.is_novel).__name__}."
            )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(
            self,
            "duplicate_signals",
            _normalize_string_list(self.duplicate_signals, "duplicate_signals"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "novelty_score": self.novelty_score,
            "max_similarity": self.max_similarity,
            "nearest_neighbor_id": self.nearest_neighbor_id,
            "similarity_threshold": self.similarity_threshold,
            "is_novel": self.is_novel,
            "summary": self.summary,
            "duplicate_signals": list(self.duplicate_signals),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "NoveltyAssessment":
        data = _validate_payload_keys(
            payload,
            field_name="NoveltyAssessment",
            required={
                "novelty_score",
                "max_similarity",
                "nearest_neighbor_id",
                "similarity_threshold",
                "is_novel",
                "summary",
                "duplicate_signals",
            },
        )
        return cls(
            novelty_score=data["novelty_score"],
            max_similarity=data["max_similarity"],
            nearest_neighbor_id=data["nearest_neighbor_id"],
            similarity_threshold=data["similarity_threshold"],
            is_novel=data["is_novel"],
            summary=data["summary"],
            duplicate_signals=data["duplicate_signals"],
        )


class AgenticNoveltyFilter:
    """Judge novelty semantically through the provider layer."""

    def __init__(
        self,
        *,
        provider: Provider,
        similarity_threshold: float = 0.8,
        max_archive_candidates: int = 12,
    ) -> None:
        self._provider = provider
        self._similarity_threshold = _normalize_probability(
            similarity_threshold,
            "similarity_threshold",
        )
        if not isinstance(max_archive_candidates, int) or max_archive_candidates <= 0:
            raise ArgusValidationError("max_archive_candidates must be a positive integer.")
        self._max_archive_candidates = max_archive_candidates

    @property
    def provider(self) -> Provider:
        return self._provider

    def assess(
        self,
        *,
        problem_spec: ProblemSpec,
        candidate: Candidate,
        archive_nodes: Iterable[Node],
    ) -> NoveltyAssessment:
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

        archive_candidates = [
            {
                "node_id": node.node_id,
                "candidate": node.candidate.to_dict(),
            }
            for node in sorted(archive_nodes, key=lambda item: item.node_id)[: self._max_archive_candidates]
        ]
        if not archive_candidates:
            return NoveltyAssessment(
                novelty_score=1.0,
                max_similarity=0.0,
                nearest_neighbor_id=None,
                similarity_threshold=self._similarity_threshold,
                is_novel=True,
                summary="Archive is empty, so the candidate is novel by default.",
                duplicate_signals=[],
            )

        response = self._provider.run_action(
            action_name="assess_novelty",
            problem_spec=problem_spec,
            input_payload={
                "candidate": candidate.to_dict(),
                "archive_candidates": archive_candidates,
                "similarity_threshold": self._similarity_threshold,
                "novelty_policy": {
                    "decision_rule": (
                        "Reject only near-duplicates or trivial rephrasings. Preserve genuinely distinct strategic directions even when they share domain vocabulary."
                    ),
                },
            },
            output_schema=novelty_assessment_schema(),
        )
        return response.payload


def novelty_assessment_schema() -> StructuredOutputSchema[NoveltyAssessment]:
    probability_field = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    return StructuredOutputSchema(
        name="novelty_assessment",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "novelty_score",
                "max_similarity",
                "nearest_neighbor_id",
                "similarity_threshold",
                "is_novel",
                "summary",
                "duplicate_signals",
            ],
            "properties": {
                "novelty_score": probability_field,
                "max_similarity": probability_field,
                "nearest_neighbor_id": {"type": ["string", "null"]},
                "similarity_threshold": probability_field,
                "is_novel": {"type": "boolean"},
                "summary": {"type": "string", "minLength": 1},
                "duplicate_signals": _string_array_schema(),
            },
        },
        validator=NoveltyAssessment.from_dict,
    )


def _string_array_schema() -> dict[str, JSONValue]:
    return {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
    }


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
