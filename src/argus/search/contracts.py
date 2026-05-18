from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from argus.errors import ArgusValidationError
from argus.models import (
    Candidate,
    Critique,
    HybridVerdict,
    JSONValue,
    LearningNote,
    ProblemSpec,
)
from argus.providers import StructuredOutputSchema


@dataclass(frozen=True, slots=True)
class ProblemFrame:
    problem_spec: ProblemSpec
    framing_candidate: Candidate
    framing_notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(self.problem_spec).__name__}."
            )
        if not isinstance(self.framing_candidate, Candidate):
            raise ArgusValidationError(
                "framing_candidate must be a Candidate instance, "
                f"got {type(self.framing_candidate).__name__}."
            )
        object.__setattr__(
            self,
            "framing_notes",
            _normalize_string_list(self.framing_notes, "framing_notes"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "problem_spec": self.problem_spec.to_dict(),
            "framing_candidate": self.framing_candidate.to_dict(),
            "framing_notes": list(self.framing_notes),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ProblemFrame":
        data = _validate_payload_keys(
            payload,
            field_name="ProblemFrame",
            required={"problem_spec", "framing_candidate", "framing_notes"},
        )
        return cls(
            problem_spec=ProblemSpec.from_dict(data["problem_spec"]),
            framing_candidate=Candidate.from_dict(data["framing_candidate"]),
            framing_notes=data["framing_notes"],
        )


@dataclass(frozen=True, slots=True)
class CandidateBatch:
    candidates: list[Candidate]
    batch_summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", _normalize_candidates(self.candidates, "candidates"))
        object.__setattr__(
            self,
            "batch_summary",
            _normalize_non_empty_string(self.batch_summary, "batch_summary"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "batch_summary": self.batch_summary,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "CandidateBatch":
        data = _validate_payload_keys(
            payload,
            field_name="CandidateBatch",
            required={"candidates", "batch_summary"},
        )
        return cls(
            candidates=[Candidate.from_dict(item) for item in _normalize_sequence(data["candidates"], "candidates")],
            batch_summary=data["batch_summary"],
        )


@dataclass(frozen=True, slots=True)
class HybridCandidateDecision:
    hybrid_name: str
    seam_hypothesis: str
    repaired_failure_mode: str
    complementary_strengths: list[str]
    complexity_tax: str
    expected_upside: str
    open_questions: list[str]
    verdict: HybridVerdict
    summary: str
    candidate: Candidate | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hybrid_name",
            _normalize_non_empty_string(self.hybrid_name, "hybrid_name"),
        )
        object.__setattr__(
            self,
            "seam_hypothesis",
            _normalize_non_empty_string(self.seam_hypothesis, "seam_hypothesis"),
        )
        object.__setattr__(
            self,
            "repaired_failure_mode",
            _normalize_non_empty_string(self.repaired_failure_mode, "repaired_failure_mode"),
        )
        object.__setattr__(
            self,
            "complementary_strengths",
            _normalize_string_list(self.complementary_strengths, "complementary_strengths"),
        )
        object.__setattr__(
            self,
            "complexity_tax",
            _normalize_non_empty_string(self.complexity_tax, "complexity_tax"),
        )
        object.__setattr__(
            self,
            "expected_upside",
            _normalize_non_empty_string(self.expected_upside, "expected_upside"),
        )
        object.__setattr__(
            self,
            "open_questions",
            _normalize_string_list(self.open_questions, "open_questions"),
        )
        object.__setattr__(
            self,
            "verdict",
            _normalize_hybrid_verdict(self.verdict, "verdict"),
        )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        candidate = self.candidate
        if candidate is not None and not isinstance(candidate, Candidate):
            raise ArgusValidationError(
                "candidate must be a Candidate instance or None, "
                f"got {type(candidate).__name__}."
            )
        if self.verdict is HybridVerdict.PURSUE and candidate is None:
            raise ArgusValidationError(
                "candidate must be provided when verdict is pursue."
            )
        if self.verdict is not HybridVerdict.PURSUE and candidate is not None:
            raise ArgusValidationError(
                "candidate must be omitted unless verdict is pursue."
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "hybrid_name": self.hybrid_name,
            "seam_hypothesis": self.seam_hypothesis,
            "repaired_failure_mode": self.repaired_failure_mode,
            "complementary_strengths": list(self.complementary_strengths),
            "complexity_tax": self.complexity_tax,
            "expected_upside": self.expected_upside,
            "open_questions": list(self.open_questions),
            "verdict": self.verdict.value,
            "summary": self.summary,
            "candidate": None,
        }
        if self.candidate is not None:
            payload["candidate"] = self.candidate.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "HybridCandidateDecision":
        data = _validate_payload_keys(
            payload,
            field_name="HybridCandidateDecision",
            required={
                "hybrid_name",
                "seam_hypothesis",
                "repaired_failure_mode",
                "complementary_strengths",
                "complexity_tax",
                "expected_upside",
                "open_questions",
                "verdict",
                "summary",
                "candidate",
            },
        )
        candidate_payload = data["candidate"]
        return cls(
            hybrid_name=data["hybrid_name"],
            seam_hypothesis=data["seam_hypothesis"],
            repaired_failure_mode=data["repaired_failure_mode"],
            complementary_strengths=data["complementary_strengths"],
            complexity_tax=data["complexity_tax"],
            expected_upside=data["expected_upside"],
            open_questions=data["open_questions"],
            verdict=data["verdict"],
            summary=data["summary"],
            candidate=None if candidate_payload is None else Candidate.from_dict(candidate_payload),
        )


@dataclass(frozen=True, slots=True)
class HybridCandidateBatch:
    decisions: list[HybridCandidateDecision]
    batch_summary: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decisions",
            _normalize_hybrid_decisions(self.decisions, "decisions"),
        )
        object.__setattr__(
            self,
            "batch_summary",
            _normalize_non_empty_string(self.batch_summary, "batch_summary"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "batch_summary": self.batch_summary,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "HybridCandidateBatch":
        data = _validate_payload_keys(
            payload,
            field_name="HybridCandidateBatch",
            required={"decisions", "batch_summary"},
        )
        return cls(
            decisions=[
                HybridCandidateDecision.from_dict(item)
                for item in _normalize_sequence(data["decisions"], "decisions")
            ],
            batch_summary=data["batch_summary"],
        )


@dataclass(frozen=True, slots=True)
class LearningCompression:
    notes: list[LearningNote]
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", _normalize_learning_notes(self.notes, "notes"))
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))

    def to_dict(self) -> dict[str, object]:
        return {
            "notes": [note.to_dict() for note in self.notes],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "LearningCompression":
        data = _validate_payload_keys(
            payload,
            field_name="LearningCompression",
            required={"notes", "summary"},
        )
        return cls(
            notes=[
                LearningNote.from_dict(item)
                for item in _normalize_sequence(data["notes"], "notes")
            ],
            summary=data["summary"],
        )


def problem_frame_schema() -> StructuredOutputSchema[ProblemFrame]:
    return StructuredOutputSchema(
        name="problem_frame",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["problem_spec", "framing_candidate", "framing_notes"],
            "properties": {
                "problem_spec": _problem_spec_schema(),
                "framing_candidate": _candidate_schema(),
                "framing_notes": _string_array_schema(),
            },
        },
        validator=ProblemFrame.from_dict,
    )


def candidate_schema() -> StructuredOutputSchema[Candidate]:
    return StructuredOutputSchema(
        name="candidate",
        json_schema=_candidate_schema(),
        validator=Candidate.from_dict,
    )


def candidate_batch_schema() -> StructuredOutputSchema[CandidateBatch]:
    return StructuredOutputSchema(
        name="candidate_batch",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["candidates", "batch_summary"],
            "properties": {
                "candidates": {
                    "type": "array",
                    "minItems": 1,
                    "items": _candidate_schema(),
                },
                "batch_summary": {"type": "string", "minLength": 1},
            },
        },
        validator=CandidateBatch.from_dict,
    )


def critique_schema() -> StructuredOutputSchema[Critique]:
    return StructuredOutputSchema(
        name="critique",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["hidden_dependencies", "kill_shots", "sharp_edges", "summary"],
            "properties": {
                "hidden_dependencies": _string_array_schema(),
                "kill_shots": _string_array_schema(),
                "sharp_edges": _string_array_schema(),
                "summary": {"type": "string", "minLength": 1},
            },
        },
        validator=Critique.from_dict,
    )


def hybrid_candidate_batch_schema() -> StructuredOutputSchema[HybridCandidateBatch]:
    return StructuredOutputSchema(
        name="hybrid_candidate_batch",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["decisions", "batch_summary"],
            "properties": {
                "decisions": {
                    "type": "array",
                    "minItems": 1,
                    "items": _hybrid_candidate_decision_schema(),
                },
                "batch_summary": {"type": "string", "minLength": 1},
            },
        },
        validator=HybridCandidateBatch.from_dict,
    )


def learning_compression_schema() -> StructuredOutputSchema[LearningCompression]:
    return StructuredOutputSchema(
        name="learning_compression",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["notes", "summary"],
            "properties": {
                "notes": {
                    "type": "array",
                    "minItems": 1,
                    "items": _learning_note_schema(),
                },
                "summary": {"type": "string", "minLength": 1},
            },
        },
        validator=LearningCompression.from_dict,
    )


def _problem_spec_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["request", "constraints", "success_criteria", "context"],
        "properties": {
            "request": {"type": "string", "minLength": 1},
            "constraints": _string_array_schema(),
            "success_criteria": _string_array_schema(),
            "context": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
                "required": [],
            },
        },
    }


def _candidate_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "thesis",
            "mechanism",
            "assumptions",
            "strengths",
            "failure_modes",
            "unknowns",
            "implementation_shape",
            "evidence",
        ],
        "properties": {
            "thesis": {"type": "string", "minLength": 1},
            "mechanism": {"type": "string", "minLength": 1},
            "assumptions": _string_array_schema(),
            "strengths": _string_array_schema(),
            "failure_modes": _string_array_schema(),
            "unknowns": _string_array_schema(),
            "implementation_shape": {
                "type": ["string", "null"],
                "minLength": 1,
            },
            "evidence": _string_array_schema(),
        },
    }


def _learning_note_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["note_type", "text", "source_node_ids"],
        "properties": {
            "note_type": {
                "type": "string",
                "enum": [
                    "winning_pattern",
                    "failure_pattern",
                    "constraint",
                    "routing_hint",
                    "summary",
                ],
            },
            "text": {"type": "string", "minLength": 1},
            "source_node_ids": _string_array_schema(),
        },
    }


def _hybrid_candidate_decision_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "hybrid_name",
            "seam_hypothesis",
            "repaired_failure_mode",
            "complementary_strengths",
            "complexity_tax",
            "expected_upside",
            "open_questions",
            "verdict",
            "summary",
            "candidate",
        ],
        "properties": {
            "hybrid_name": {"type": "string", "minLength": 1},
            "seam_hypothesis": {"type": "string", "minLength": 1},
            "repaired_failure_mode": {"type": "string", "minLength": 1},
            "complementary_strengths": _string_array_schema(),
            "complexity_tax": {"type": "string", "minLength": 1},
            "expected_upside": {"type": "string", "minLength": 1},
            "open_questions": _string_array_schema(),
            "verdict": {
                "type": "string",
                "enum": [
                    HybridVerdict.PURSUE.value,
                    HybridVerdict.HOLD.value,
                    HybridVerdict.REJECT.value,
                ],
            },
            "summary": {"type": "string", "minLength": 1},
            "candidate": _nullable_object_schema(_candidate_schema()),
        },
    }


def _nullable_object_schema(schema: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    schema_type = schema.get("type")
    if schema_type != "object":
        raise ArgusValidationError(
            "_nullable_object_schema requires an object schema, "
            f"got {schema_type!r}."
        )
    return {
        **dict(schema),
        "type": ["object", "null"],
    }


def _string_array_schema() -> dict[str, JSONValue]:
    return {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
    }


def _normalize_candidates(value: object, field_name: str) -> list[Candidate]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list of candidates, got {type(value).__name__}."
        )
    normalized: list[Candidate] = []
    for index, item in enumerate(value):
        if not isinstance(item, Candidate):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a Candidate instance, got {type(item).__name__}."
            )
        normalized.append(item)
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _normalize_learning_notes(value: object, field_name: str) -> list[LearningNote]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list of learning notes, got {type(value).__name__}."
        )
    normalized: list[LearningNote] = []
    for index, item in enumerate(value):
        if not isinstance(item, LearningNote):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a LearningNote instance, got {type(item).__name__}."
            )
        normalized.append(item)
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _normalize_hybrid_decisions(
    value: object,
    field_name: str,
) -> list[HybridCandidateDecision]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list of hybrid decisions, got {type(value).__name__}."
        )
    normalized: list[HybridCandidateDecision] = []
    for index, item in enumerate(value):
        if not isinstance(item, HybridCandidateDecision):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a HybridCandidateDecision instance, "
                f"got {type(item).__name__}."
            )
        normalized.append(item)
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


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
    normalized = _normalize_sequence(value, field_name)
    strings: list[str] = []
    for index, item in enumerate(normalized):
        strings.append(_normalize_non_empty_string(item, f"{field_name}[{index}]"))
    return strings


def _normalize_hybrid_verdict(value: object, field_name: str) -> HybridVerdict:
    if isinstance(value, HybridVerdict):
        return value
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a HybridVerdict or string, got {type(value).__name__}."
        )
    normalized = value.strip()
    try:
        return HybridVerdict(normalized)
    except ValueError as exc:
        supported = ", ".join(verdict.value for verdict in HybridVerdict)
        raise ArgusValidationError(
            f"{field_name} must be one of: {supported}."
        ) from exc


def _normalize_sequence(value: object, field_name: str) -> list[object]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(value).__name__}."
        )
    return list(value)


def _validate_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ArgusValidationError(
            f"{field_name} payload must be a mapping, got {type(payload).__name__}."
        )
    keys = set(payload)
    missing = required - keys
    unexpected = keys - required
    if missing:
        joined = ", ".join(sorted(missing))
        raise ArgusValidationError(f"{field_name} payload is missing required keys: {joined}.")
    if unexpected:
        joined = ", ".join(sorted(unexpected))
        raise ArgusValidationError(
            f"{field_name} payload contains unexpected keys: {joined}."
        )
    return dict(payload)


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)
