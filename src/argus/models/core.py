from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import math
import re

from argus.errors import ArgusValidationError

type JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


class ActionType(StrEnum):
    FRAME_PROBLEM = "frame_problem"
    GENERATE_SEED = "generate_seed"
    MUTATE = "mutate"
    COMBINE = "combine"
    STRESS_TEST = "stress_test"
    DEEPEN = "deepen"
    RANK = "rank"
    COMPRESS_LEARNING = "compress_learning"


class NodeLifecycleStatus(StrEnum):
    PENDING = "pending"
    ADMITTED = "admitted"
    ARCHIVED = "archived"
    PRUNED = "pruned"
    REJECTED = "rejected"
    FAILED = "failed"
    WINNER = "winner"


class LearningNoteType(StrEnum):
    WINNING_PATTERN = "winning_pattern"
    FAILURE_PATTERN = "failure_pattern"
    CONSTRAINT = "constraint"
    ROUTING_HINT = "routing_hint"
    SUMMARY = "summary"


class LearningEvidenceSource(StrEnum):
    SEARCH_RUN = "search_run"
    OUTCOME_FEEDBACK = "outcome_feedback"


class OutcomeFeedbackStatus(StrEnum):
    VALIDATED = "validated"
    MIXED = "mixed"
    INVALIDATED = "invalidated"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class ProblemSpec:
    request: str
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    context: dict[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _normalize_non_empty_string(self.request, "request"))
        object.__setattr__(
            self,
            "constraints",
            _normalize_string_list(self.constraints, "constraints"),
        )
        object.__setattr__(
            self,
            "success_criteria",
            _normalize_string_list(self.success_criteria, "success_criteria"),
        )
        object.__setattr__(self, "context", _normalize_json_object(self.context, "context"))

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request,
            "constraints": list(self.constraints),
            "success_criteria": list(self.success_criteria),
            "context": _copy_json_object(self.context),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ProblemSpec":
        data = _validate_payload_keys(
            payload,
            field_name="ProblemSpec",
            required={"request", "constraints", "success_criteria", "context"},
        )
        return cls(
            request=data["request"],
            constraints=data["constraints"],
            success_criteria=data["success_criteria"],
            context=data["context"],
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    thesis: str
    mechanism: str
    assumptions: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    implementation_shape: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "thesis", _normalize_non_empty_string(self.thesis, "thesis"))
        object.__setattr__(
            self,
            "mechanism",
            _normalize_non_empty_string(self.mechanism, "mechanism"),
        )
        object.__setattr__(
            self,
            "assumptions",
            _normalize_string_list(self.assumptions, "assumptions"),
        )
        object.__setattr__(self, "strengths", _normalize_string_list(self.strengths, "strengths"))
        object.__setattr__(
            self,
            "failure_modes",
            _normalize_string_list(self.failure_modes, "failure_modes"),
        )
        object.__setattr__(self, "unknowns", _normalize_string_list(self.unknowns, "unknowns"))
        object.__setattr__(
            self,
            "implementation_shape",
            _normalize_optional_string(self.implementation_shape, "implementation_shape"),
        )
        object.__setattr__(self, "evidence", _normalize_string_list(self.evidence, "evidence"))

    def text_projection(self) -> str:
        sections = [
            ("thesis", [self.thesis]),
            ("mechanism", [self.mechanism]),
            ("assumptions", self.assumptions),
            ("strengths", self.strengths),
            ("failure_modes", self.failure_modes),
            ("unknowns", self.unknowns),
            ("evidence", self.evidence),
        ]
        if self.implementation_shape is not None:
            sections.append(("implementation_shape", [self.implementation_shape]))

        lines: list[str] = []
        for label, values in sections:
            lines.append(f"{label}:")
            lines.extend(f"- {value}" for value in values)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "thesis": self.thesis,
            "mechanism": self.mechanism,
            "assumptions": list(self.assumptions),
            "strengths": list(self.strengths),
            "failure_modes": list(self.failure_modes),
            "unknowns": list(self.unknowns),
            "evidence": list(self.evidence),
        }
        if self.implementation_shape is not None:
            payload["implementation_shape"] = self.implementation_shape
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "Candidate":
        data = _validate_payload_keys(
            payload,
            field_name="Candidate",
            required={
                "thesis",
                "mechanism",
                "assumptions",
                "strengths",
                "failure_modes",
                "unknowns",
                "evidence",
            },
            optional={"implementation_shape"},
        )
        return cls(
            thesis=data["thesis"],
            mechanism=data["mechanism"],
            assumptions=data["assumptions"],
            strengths=data["strengths"],
            failure_modes=data["failure_modes"],
            unknowns=data["unknowns"],
            implementation_shape=data.get("implementation_shape"),
            evidence=data["evidence"],
        )


@dataclass(frozen=True, slots=True)
class ScoreVector:
    hard_constraint_pass: bool
    hard_constraint_reasons: list[str] = field(default_factory=list)
    distinctiveness: float = 0.0
    usefulness: float = 0.0
    specificity: float = 0.0
    plausibility: float = 0.0
    implementation_tractability: float = 0.0
    upside: float = 0.0
    adversarial_robustness: float = 0.0
    evidence_quality: float = 0.0
    total_score: float = 0.0
    confidence_estimate: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.hard_constraint_pass, bool):
            raise ArgusValidationError(
                "hard_constraint_pass must be a boolean, "
                f"got {type(self.hard_constraint_pass).__name__}."
            )
        object.__setattr__(
            self,
            "hard_constraint_reasons",
            _normalize_string_list(self.hard_constraint_reasons, "hard_constraint_reasons"),
        )
        if not self.hard_constraint_pass and not self.hard_constraint_reasons:
            raise ArgusValidationError(
                "hard_constraint_reasons must be populated when hard_constraint_pass is false."
            )

        score_fields = (
            "distinctiveness",
            "usefulness",
            "specificity",
            "plausibility",
            "implementation_tractability",
            "upside",
            "adversarial_robustness",
            "evidence_quality",
            "total_score",
        )
        for field_name in score_fields:
            object.__setattr__(
                self,
                field_name,
                _normalize_float(getattr(self, field_name), field_name),
            )

        object.__setattr__(
            self,
            "confidence_estimate",
            _normalize_probability(self.confidence_estimate, "confidence_estimate"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "hard_constraint_pass": self.hard_constraint_pass,
            "hard_constraint_reasons": list(self.hard_constraint_reasons),
            "distinctiveness": self.distinctiveness,
            "usefulness": self.usefulness,
            "specificity": self.specificity,
            "plausibility": self.plausibility,
            "implementation_tractability": self.implementation_tractability,
            "upside": self.upside,
            "adversarial_robustness": self.adversarial_robustness,
            "evidence_quality": self.evidence_quality,
            "total_score": self.total_score,
            "confidence_estimate": self.confidence_estimate,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ScoreVector":
        data = _validate_payload_keys(
            payload,
            field_name="ScoreVector",
            required={
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
            },
        )
        return cls(
            hard_constraint_pass=data["hard_constraint_pass"],
            hard_constraint_reasons=data["hard_constraint_reasons"],
            distinctiveness=data["distinctiveness"],
            usefulness=data["usefulness"],
            specificity=data["specificity"],
            plausibility=data["plausibility"],
            implementation_tractability=data["implementation_tractability"],
            upside=data["upside"],
            adversarial_robustness=data["adversarial_robustness"],
            evidence_quality=data["evidence_quality"],
            total_score=data["total_score"],
            confidence_estimate=data["confidence_estimate"],
        )


@dataclass(frozen=True, slots=True)
class Critique:
    hidden_dependencies: list[str] = field(default_factory=list)
    kill_shots: list[str] = field(default_factory=list)
    sharp_edges: list[str] = field(default_factory=list)
    summary: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hidden_dependencies",
            _normalize_string_list(self.hidden_dependencies, "hidden_dependencies"),
        )
        object.__setattr__(self, "kill_shots", _normalize_string_list(self.kill_shots, "kill_shots"))
        object.__setattr__(
            self,
            "sharp_edges",
            _normalize_string_list(self.sharp_edges, "sharp_edges"),
        )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))

    def to_dict(self) -> dict[str, object]:
        return {
            "hidden_dependencies": list(self.hidden_dependencies),
            "kill_shots": list(self.kill_shots),
            "sharp_edges": list(self.sharp_edges),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "Critique":
        data = _validate_payload_keys(
            payload,
            field_name="Critique",
            required={"hidden_dependencies", "kill_shots", "sharp_edges", "summary"},
        )
        return cls(
            hidden_dependencies=data["hidden_dependencies"],
            kill_shots=data["kill_shots"],
            sharp_edges=data["sharp_edges"],
            summary=data["summary"],
        )


@dataclass(frozen=True, slots=True)
class Node:
    node_id: str
    parent_ids: list[str]
    depth: int
    action_type: ActionType
    provider_name: str
    candidate: Candidate
    island_id: str | None = None
    score: ScoreVector | None = None
    critique: Critique | None = None
    novelty_score: float = 0.0
    lifecycle_status: NodeLifecycleStatus = NodeLifecycleStatus.PENDING
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _normalize_non_empty_string(self.node_id, "node_id"))
        object.__setattr__(
            self,
            "parent_ids",
            _normalize_unique_string_list(self.parent_ids, "parent_ids"),
        )
        object.__setattr__(self, "depth", _normalize_non_negative_int(self.depth, "depth"))
        object.__setattr__(
            self,
            "action_type",
            _normalize_enum(self.action_type, ActionType, "action_type"),
        )
        object.__setattr__(
            self,
            "provider_name",
            _normalize_non_empty_string(self.provider_name, "provider_name"),
        )
        object.__setattr__(
            self,
            "island_id",
            _normalize_optional_string(self.island_id, "island_id"),
        )
        if not isinstance(self.candidate, Candidate):
            raise ArgusValidationError(
                f"candidate must be a Candidate instance, got {type(self.candidate).__name__}."
            )
        if self.score is not None and not isinstance(self.score, ScoreVector):
            raise ArgusValidationError(
                f"score must be a ScoreVector or None, got {type(self.score).__name__}."
            )
        if self.critique is not None and not isinstance(self.critique, Critique):
            raise ArgusValidationError(
                f"critique must be a Critique or None, got {type(self.critique).__name__}."
            )
        object.__setattr__(self, "novelty_score", _normalize_probability(self.novelty_score, "novelty_score"))
        object.__setattr__(
            self,
            "lifecycle_status",
            _normalize_enum(self.lifecycle_status, NodeLifecycleStatus, "lifecycle_status"),
        )
        object.__setattr__(self, "metadata", _normalize_json_object(self.metadata, "metadata"))
        object.__setattr__(self, "created_at", _normalize_datetime(self.created_at, "created_at"))

        if self.parent_ids and self.depth == 0:
            raise ArgusValidationError("depth must be greater than 0 when parent_ids are present.")
        if not self.parent_ids and self.depth != 0:
            raise ArgusValidationError("depth must be 0 when parent_ids is empty.")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "node_id": self.node_id,
            "parent_ids": list(self.parent_ids),
            "depth": self.depth,
            "action_type": self.action_type.value,
            "provider_name": self.provider_name,
            "candidate": self.candidate.to_dict(),
            "novelty_score": self.novelty_score,
            "lifecycle_status": self.lifecycle_status.value,
            "metadata": _copy_json_object(self.metadata),
            "created_at": _dump_datetime(self.created_at),
        }
        if self.island_id is not None:
            payload["island_id"] = self.island_id
        if self.score is not None:
            payload["score"] = self.score.to_dict()
        if self.critique is not None:
            payload["critique"] = self.critique.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "Node":
        data = _validate_payload_keys(
            payload,
            field_name="Node",
            required={
                "node_id",
                "parent_ids",
                "depth",
                "action_type",
                "provider_name",
                "candidate",
                "novelty_score",
                "lifecycle_status",
                "metadata",
                "created_at",
            },
            optional={"island_id", "score", "critique"},
        )
        score_payload = data.get("score")
        critique_payload = data.get("critique")
        return cls(
            node_id=data["node_id"],
            parent_ids=data["parent_ids"],
            depth=data["depth"],
            action_type=data["action_type"],
            provider_name=data["provider_name"],
            candidate=Candidate.from_dict(data["candidate"]),
            island_id=data.get("island_id"),
            score=None if score_payload is None else ScoreVector.from_dict(score_payload),
            critique=None if critique_payload is None else Critique.from_dict(critique_payload),
            novelty_score=data["novelty_score"],
            lifecycle_status=data["lifecycle_status"],
            metadata=data["metadata"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True, slots=True)
class LearningNote:
    note_type: LearningNoteType
    text: str
    source_node_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "note_type",
            _normalize_enum(self.note_type, LearningNoteType, "note_type"),
        )
        object.__setattr__(self, "text", _normalize_non_empty_string(self.text, "text"))
        object.__setattr__(
            self,
            "source_node_ids",
            _normalize_unique_string_list(self.source_node_ids, "source_node_ids"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "note_type": self.note_type.value,
            "text": self.text,
            "source_node_ids": list(self.source_node_ids),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "LearningNote":
        data = _validate_payload_keys(
            payload,
            field_name="LearningNote",
            required={"note_type", "text", "source_node_ids"},
        )
        return cls(
            note_type=data["note_type"],
            text=data["text"],
            source_node_ids=data["source_node_ids"],
        )


@dataclass(frozen=True, slots=True)
class OutcomeFeedback:
    feedback_id: str
    run_id: str
    node_id: str
    candidate_thesis: str
    problem_statement: str
    outcome_status: OutcomeFeedbackStatus
    summary: str
    learning_notes: list[LearningNote] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    experiment_label: str | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "feedback_id", _normalize_non_empty_string(self.feedback_id, "feedback_id"))
        object.__setattr__(self, "run_id", _normalize_non_empty_string(self.run_id, "run_id"))
        object.__setattr__(self, "node_id", _normalize_non_empty_string(self.node_id, "node_id"))
        object.__setattr__(
            self,
            "candidate_thesis",
            _normalize_non_empty_string(self.candidate_thesis, "candidate_thesis"),
        )
        object.__setattr__(
            self,
            "problem_statement",
            _normalize_non_empty_string(self.problem_statement, "problem_statement"),
        )
        object.__setattr__(
            self,
            "outcome_status",
            _normalize_enum(self.outcome_status, OutcomeFeedbackStatus, "outcome_status"),
        )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(
            self,
            "learning_notes",
            _normalize_outcome_feedback_learning_notes(
                self.learning_notes,
                node_id=self.node_id,
            ),
        )
        object.__setattr__(self, "evidence", _normalize_string_list(self.evidence, "evidence"))
        object.__setattr__(
            self,
            "experiment_label",
            _normalize_optional_string(self.experiment_label, "experiment_label"),
        )
        object.__setattr__(
            self,
            "recorded_at",
            _normalize_datetime(self.recorded_at, "recorded_at"),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "feedback_id": self.feedback_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "candidate_thesis": self.candidate_thesis,
            "problem_statement": self.problem_statement,
            "outcome_status": self.outcome_status.value,
            "summary": self.summary,
            "learning_notes": [note.to_dict() for note in self.learning_notes],
            "evidence": list(self.evidence),
            "recorded_at": _dump_datetime(self.recorded_at),
        }
        if self.experiment_label is not None:
            payload["experiment_label"] = self.experiment_label
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "OutcomeFeedback":
        data = _validate_payload_keys(
            payload,
            field_name="OutcomeFeedback",
            required={
                "feedback_id",
                "run_id",
                "node_id",
                "candidate_thesis",
                "problem_statement",
                "outcome_status",
                "summary",
                "learning_notes",
                "evidence",
                "recorded_at",
            },
            optional={"experiment_label"},
        )
        return cls(
            feedback_id=data["feedback_id"],
            run_id=data["run_id"],
            node_id=data["node_id"],
            candidate_thesis=data["candidate_thesis"],
            problem_statement=data["problem_statement"],
            outcome_status=data["outcome_status"],
            summary=data["summary"],
            learning_notes=[
                LearningNote.from_dict(item)
                for item in _normalize_sequence(data["learning_notes"], "learning_notes")
            ],
            evidence=data["evidence"],
            experiment_label=data.get("experiment_label"),
            recorded_at=data["recorded_at"],
        )


@dataclass(frozen=True, slots=True)
class ReusableLearningNote:
    note_id: str
    note_type: LearningNoteType
    text: str
    evidence_sources: list[LearningEvidenceSource] = field(
        default_factory=lambda: [LearningEvidenceSource.SEARCH_RUN]
    )
    source_run_ids: list[str] = field(default_factory=list)
    source_node_refs: list[str] = field(default_factory=list)
    problem_statements: list[str] = field(default_factory=list)
    observation_count: int = 1
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "note_id", _normalize_non_empty_string(self.note_id, "note_id"))
        object.__setattr__(
            self,
            "note_type",
            _normalize_enum(self.note_type, LearningNoteType, "note_type"),
        )
        object.__setattr__(self, "text", _normalize_non_empty_string(self.text, "text"))
        object.__setattr__(
            self,
            "evidence_sources",
            _normalize_learning_evidence_sources(self.evidence_sources, "evidence_sources"),
        )
        object.__setattr__(
            self,
            "source_run_ids",
            _normalize_unique_string_list(self.source_run_ids, "source_run_ids"),
        )
        object.__setattr__(
            self,
            "source_node_refs",
            _normalize_unique_string_list(self.source_node_refs, "source_node_refs"),
        )
        object.__setattr__(
            self,
            "problem_statements",
            _normalize_unique_string_list(self.problem_statements, "problem_statements"),
        )
        object.__setattr__(
            self,
            "observation_count",
            _normalize_positive_int(self.observation_count, "observation_count"),
        )
        object.__setattr__(
            self,
            "first_seen_at",
            _normalize_datetime(self.first_seen_at, "first_seen_at"),
        )
        object.__setattr__(
            self,
            "last_seen_at",
            _normalize_datetime(self.last_seen_at, "last_seen_at"),
        )
        if self.last_seen_at < self.first_seen_at:
            raise ArgusValidationError("last_seen_at must not be earlier than first_seen_at.")

    def to_dict(self) -> dict[str, object]:
        return {
            "note_id": self.note_id,
            "note_type": self.note_type.value,
            "text": self.text,
            "evidence_sources": [source.value for source in self.evidence_sources],
            "source_run_ids": list(self.source_run_ids),
            "source_node_refs": list(self.source_node_refs),
            "problem_statements": list(self.problem_statements),
            "observation_count": self.observation_count,
            "first_seen_at": _dump_datetime(self.first_seen_at),
            "last_seen_at": _dump_datetime(self.last_seen_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ReusableLearningNote":
        data = _validate_payload_keys(
            payload,
            field_name="ReusableLearningNote",
            required={
                "note_id",
                "note_type",
                "text",
                "source_run_ids",
                "source_node_refs",
                "problem_statements",
                "observation_count",
                "first_seen_at",
                "last_seen_at",
            },
            optional={"evidence_sources"},
        )
        return cls(
            note_id=data["note_id"],
            note_type=data["note_type"],
            text=data["text"],
            evidence_sources=data.get("evidence_sources", [LearningEvidenceSource.SEARCH_RUN.value]),
            source_run_ids=data["source_run_ids"],
            source_node_refs=data["source_node_refs"],
            problem_statements=data["problem_statements"],
            observation_count=data["observation_count"],
            first_seen_at=data["first_seen_at"],
            last_seen_at=data["last_seen_at"],
        )

    @classmethod
    def from_learning_note(
        cls,
        *,
        run_id: str,
        problem_spec: ProblemSpec,
        note: LearningNote,
        observed_at: datetime | None = None,
        evidence_source: LearningEvidenceSource = LearningEvidenceSource.SEARCH_RUN,
    ) -> "ReusableLearningNote":
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        if not isinstance(note, LearningNote):
            raise ArgusValidationError(
                f"note must be a LearningNote instance, got {type(note).__name__}."
            )
        timestamp = _normalize_datetime(
            observed_at or datetime.now(timezone.utc),
            "observed_at",
        )
        normalized_run_id = _normalize_non_empty_string(run_id, "run_id")
        return cls(
            note_id=_build_reusable_learning_note_id(note.note_type, note.text),
            note_type=note.note_type,
            text=note.text,
            evidence_sources=[evidence_source],
            source_run_ids=[normalized_run_id],
            source_node_refs=[
                f"{normalized_run_id}:{node_id}" for node_id in note.source_node_ids
            ],
            problem_statements=[problem_spec.request],
            observation_count=1,
            first_seen_at=timestamp,
            last_seen_at=timestamp,
        )

    @classmethod
    def from_outcome_feedback(
        cls,
        *,
        feedback: OutcomeFeedback,
        note: LearningNote,
    ) -> "ReusableLearningNote":
        if not isinstance(feedback, OutcomeFeedback):
            raise ArgusValidationError(
                "feedback must be an OutcomeFeedback instance, "
                f"got {type(feedback).__name__}."
            )
        if not isinstance(note, LearningNote):
            raise ArgusValidationError(
                f"note must be a LearningNote instance, got {type(note).__name__}."
            )
        return cls(
            note_id=_build_reusable_learning_note_id(note.note_type, note.text),
            note_type=note.note_type,
            text=note.text,
            evidence_sources=[LearningEvidenceSource.OUTCOME_FEEDBACK],
            source_run_ids=[feedback.run_id],
            source_node_refs=[
                f"{feedback.run_id}:{node_id}" for node_id in note.source_node_ids
            ],
            problem_statements=[feedback.problem_statement],
            observation_count=1,
            first_seen_at=feedback.recorded_at,
            last_seen_at=feedback.recorded_at,
        )

    def merge(self, other: "ReusableLearningNote") -> "ReusableLearningNote":
        if not isinstance(other, ReusableLearningNote):
            raise ArgusValidationError(
                "other must be a ReusableLearningNote instance, "
                f"got {type(other).__name__}."
            )
        if self.note_id != other.note_id or self.note_type != other.note_type or self.text != other.text:
            raise ArgusValidationError(
                "Cannot merge reusable learning notes with different identities."
            )
        return ReusableLearningNote(
            note_id=self.note_id,
            note_type=self.note_type,
            text=self.text,
            evidence_sources=_merge_unique_enums(
                self.evidence_sources,
                other.evidence_sources,
            ),
            source_run_ids=_merge_unique_strings(self.source_run_ids, other.source_run_ids),
            source_node_refs=_merge_unique_strings(
                self.source_node_refs,
                other.source_node_refs,
            ),
            problem_statements=_merge_unique_strings(
                self.problem_statements,
                other.problem_statements,
            ),
            observation_count=self.observation_count + other.observation_count,
            first_seen_at=min(self.first_seen_at, other.first_seen_at),
            last_seen_at=max(self.last_seen_at, other.last_seen_at),
        )

    def to_prompt_dict(self) -> dict[str, JSONValue]:
        return {
            "note_id": self.note_id,
            "note_type": self.note_type.value,
            "text": self.text,
            "evidence_sources": [source.value for source in self.evidence_sources],
            "observation_count": self.observation_count,
            "source_run_ids": list(self.source_run_ids[:3]),
            "problem_statements": list(self.problem_statements[:2]),
        }


@dataclass(frozen=True, slots=True)
class LearningMemory:
    entries: list[ReusableLearningNote] = field(default_factory=list)
    schema_version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entries",
            _normalize_reusable_learning_entries(self.entries, "entries"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _normalize_positive_int(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _normalize_datetime(self.updated_at, "updated_at"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "schema_version": self.schema_version,
            "updated_at": _dump_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "LearningMemory":
        data = _validate_payload_keys(
            payload,
            field_name="LearningMemory",
            required={"entries", "schema_version", "updated_at"},
        )
        return cls(
            entries=[
                ReusableLearningNote.from_dict(item)
                for item in _normalize_sequence(data["entries"], "entries")
            ],
            schema_version=data["schema_version"],
            updated_at=data["updated_at"],
        )

    @classmethod
    def empty(cls) -> "LearningMemory":
        return cls(entries=[])

    def merge(self, other: "LearningMemory") -> "LearningMemory":
        if not isinstance(other, LearningMemory):
            raise ArgusValidationError(
                "other must be a LearningMemory instance, "
                f"got {type(other).__name__}."
            )
        if not self.entries:
            return other
        if not other.entries:
            return self
        merged: dict[str, ReusableLearningNote] = {
            entry.note_id: entry for entry in self.entries
        }
        for entry in other.entries:
            if entry.note_id in merged:
                merged[entry.note_id] = merged[entry.note_id].merge(entry)
            else:
                merged[entry.note_id] = entry
        return LearningMemory(
            entries=_sort_reusable_learning_entries(merged.values()),
            schema_version=max(self.schema_version, other.schema_version),
            updated_at=max(self.updated_at, other.updated_at),
        )

    def merge_observations(
        self,
        *,
        run_id: str,
        problem_spec: ProblemSpec,
        notes: Sequence[LearningNote],
        observed_at: datetime | None = None,
    ) -> "LearningMemory":
        normalized_notes = _normalize_learning_notes(notes)
        if not normalized_notes:
            return self
        timestamp = _normalize_datetime(
            observed_at or datetime.now(timezone.utc),
            "observed_at",
        )
        observed_entries: dict[str, ReusableLearningNote] = {}
        for note in normalized_notes:
            entry = ReusableLearningNote.from_learning_note(
                run_id=run_id,
                problem_spec=problem_spec,
                note=note,
                observed_at=timestamp,
            )
            if entry.note_id in observed_entries:
                observed_entries[entry.note_id] = observed_entries[entry.note_id].merge(entry)
            else:
                observed_entries[entry.note_id] = entry
        return self.merge(
            LearningMemory(
                entries=_sort_reusable_learning_entries(observed_entries.values()),
                schema_version=self.schema_version,
                updated_at=timestamp,
            )
        )

    def merge_outcome_feedback(
        self,
        feedback: OutcomeFeedback,
    ) -> "LearningMemory":
        if not isinstance(feedback, OutcomeFeedback):
            raise ArgusValidationError(
                "feedback must be an OutcomeFeedback instance, "
                f"got {type(feedback).__name__}."
            )
        observed_entries: dict[str, ReusableLearningNote] = {}
        for note in feedback.learning_notes:
            entry = ReusableLearningNote.from_outcome_feedback(
                feedback=feedback,
                note=note,
            )
            if entry.note_id in observed_entries:
                observed_entries[entry.note_id] = observed_entries[entry.note_id].merge(entry)
            else:
                observed_entries[entry.note_id] = entry
        if not observed_entries:
            return self
        return self.merge(
            LearningMemory(
                entries=_sort_reusable_learning_entries(observed_entries.values()),
                schema_version=self.schema_version,
                updated_at=feedback.recorded_at,
            )
        )

    def select_for_problem(
        self,
        problem_spec: ProblemSpec,
        *,
        limit: int,
    ) -> "LearningMemory":
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        normalized_limit = _normalize_positive_int(limit, "limit")
        if not self.entries:
            return LearningMemory(
                entries=[],
                schema_version=self.schema_version,
                updated_at=self.updated_at,
            )

        query_tokens = _problem_query_tokens(problem_spec)
        overlap_by_note_id = {
            entry.note_id: len(query_tokens & _reusable_learning_tokens(entry))
            for entry in self.entries
        }
        ordered = sorted(
            self.entries,
            key=lambda entry: (
                1 if overlap_by_note_id[entry.note_id] > 0 else 0,
                overlap_by_note_id[entry.note_id],
                _reusable_learning_evidence_priority(entry),
                entry.observation_count,
                _reusable_learning_type_priority(entry.note_type),
                entry.last_seen_at,
                entry.note_id,
            ),
            reverse=True,
        )
        selected = ordered[:normalized_limit]
        return LearningMemory(
            entries=selected,
            schema_version=self.schema_version,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class OutcomeFeedbackLedger:
    entries: list[OutcomeFeedback] = field(default_factory=list)
    schema_version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entries",
            _normalize_outcome_feedback_entries(self.entries, "entries"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _normalize_positive_int(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _normalize_datetime(self.updated_at, "updated_at"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "schema_version": self.schema_version,
            "updated_at": _dump_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "OutcomeFeedbackLedger":
        data = _validate_payload_keys(
            payload,
            field_name="OutcomeFeedbackLedger",
            required={"entries", "schema_version", "updated_at"},
        )
        return cls(
            entries=[
                OutcomeFeedback.from_dict(item)
                for item in _normalize_sequence(data["entries"], "entries")
            ],
            schema_version=data["schema_version"],
            updated_at=data["updated_at"],
        )

    @classmethod
    def empty(cls) -> "OutcomeFeedbackLedger":
        return cls(entries=[])

    def append(self, feedback: OutcomeFeedback) -> "OutcomeFeedbackLedger":
        if not isinstance(feedback, OutcomeFeedback):
            raise ArgusValidationError(
                "feedback must be an OutcomeFeedback instance, "
                f"got {type(feedback).__name__}."
            )
        existing = {entry.feedback_id for entry in self.entries}
        if feedback.feedback_id in existing:
            raise ArgusValidationError(
                f"Outcome feedback already exists: {feedback.feedback_id}."
            )
        ordered = sorted(
            [*self.entries, feedback],
            key=lambda entry: (entry.recorded_at, entry.feedback_id),
        )
        return OutcomeFeedbackLedger(
            entries=ordered,
            schema_version=self.schema_version,
            updated_at=feedback.recorded_at
            if not self.entries
            else max(self.updated_at, feedback.recorded_at),
        )

    def for_run(self, run_id: str) -> "OutcomeFeedbackLedger":
        normalized_run_id = _normalize_non_empty_string(run_id, "run_id")
        return OutcomeFeedbackLedger(
            entries=[
                entry for entry in self.entries if entry.run_id == normalized_run_id
            ],
            schema_version=self.schema_version,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class SearchIsland:
    island_id: str
    label: str
    description: str
    archive_ids: list[str] = field(default_factory=list)
    frontier_ids: list[str] = field(default_factory=list)
    pruned_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "island_id", _normalize_non_empty_string(self.island_id, "island_id"))
        object.__setattr__(self, "label", _normalize_non_empty_string(self.label, "label"))
        object.__setattr__(self, "description", _normalize_non_empty_string(self.description, "description"))
        object.__setattr__(
            self,
            "archive_ids",
            _normalize_unique_string_list(self.archive_ids, "archive_ids"),
        )
        object.__setattr__(
            self,
            "frontier_ids",
            _normalize_unique_string_list(self.frontier_ids, "frontier_ids"),
        )
        object.__setattr__(
            self,
            "pruned_ids",
            _normalize_unique_string_list(self.pruned_ids, "pruned_ids"),
        )

        archive_ids = set(self.archive_ids)
        unknown_frontier_ids = [node_id for node_id in self.frontier_ids if node_id not in archive_ids]
        if unknown_frontier_ids:
            joined = ", ".join(sorted(unknown_frontier_ids))
            raise ArgusValidationError(
                "frontier_ids must be a subset of archive_ids within each island: "
                f"{joined}."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "island_id": self.island_id,
            "label": self.label,
            "description": self.description,
            "archive_ids": list(self.archive_ids),
            "frontier_ids": list(self.frontier_ids),
            "pruned_ids": list(self.pruned_ids),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SearchIsland":
        data = _validate_payload_keys(
            payload,
            field_name="SearchIsland",
            required={
                "island_id",
                "label",
                "description",
                "archive_ids",
                "frontier_ids",
                "pruned_ids",
            },
        )
        return cls(
            island_id=data["island_id"],
            label=data["label"],
            description=data["description"],
            archive_ids=data["archive_ids"],
            frontier_ids=data["frontier_ids"],
            pruned_ids=data["pruned_ids"],
        )


@dataclass(frozen=True, slots=True)
class SearchState:
    problem_spec: ProblemSpec
    root_id: str
    nodes: dict[str, Node] = field(default_factory=dict)
    archive_ids: list[str] = field(default_factory=list)
    frontier_ids: list[str] = field(default_factory=list)
    pruned_ids: list[str] = field(default_factory=list)
    winner_ids: list[str] = field(default_factory=list)
    islands: dict[str, SearchIsland] = field(default_factory=dict)
    learning_notes: list[LearningNote] = field(default_factory=list)
    budget_spent: int = 0
    step_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(self.problem_spec).__name__}."
            )
        object.__setattr__(self, "root_id", _normalize_non_empty_string(self.root_id, "root_id"))
        object.__setattr__(self, "nodes", _normalize_node_map(self.nodes))
        object.__setattr__(self, "archive_ids", _normalize_unique_string_list(self.archive_ids, "archive_ids"))
        object.__setattr__(self, "frontier_ids", _normalize_unique_string_list(self.frontier_ids, "frontier_ids"))
        object.__setattr__(self, "pruned_ids", _normalize_unique_string_list(self.pruned_ids, "pruned_ids"))
        object.__setattr__(self, "winner_ids", _normalize_unique_string_list(self.winner_ids, "winner_ids"))
        object.__setattr__(self, "islands", _normalize_search_island_map(self.islands))
        object.__setattr__(
            self,
            "learning_notes",
            _normalize_learning_notes(self.learning_notes),
        )
        object.__setattr__(
            self,
            "budget_spent",
            _normalize_non_negative_int(self.budget_spent, "budget_spent"),
        )
        object.__setattr__(
            self,
            "step_count",
            _normalize_non_negative_int(self.step_count, "step_count"),
        )

        node_ids = set(self.nodes)
        if self.root_id not in node_ids:
            raise ArgusValidationError(f"root_id must exist in nodes, got {self.root_id!r}.")

        for field_name, ids in (
            ("archive_ids", self.archive_ids),
            ("frontier_ids", self.frontier_ids),
            ("pruned_ids", self.pruned_ids),
            ("winner_ids", self.winner_ids),
        ):
            unknown_ids = [node_id for node_id in ids if node_id not in node_ids]
            if unknown_ids:
                joined = ", ".join(sorted(unknown_ids))
                raise ArgusValidationError(f"{field_name} contains unknown node ids: {joined}.")

        for island in self.islands.values():
            if self.root_id not in island.archive_ids:
                raise ArgusValidationError(
                    f"island {island.island_id!r} must include the root node in archive_ids."
                )
            for field_name, ids, aggregate_ids in (
                ("archive_ids", island.archive_ids, self.archive_ids),
                ("frontier_ids", island.frontier_ids, self.frontier_ids),
                ("pruned_ids", island.pruned_ids, self.pruned_ids),
            ):
                missing = [node_id for node_id in ids if node_id not in aggregate_ids]
                if missing:
                    joined = ", ".join(sorted(missing))
                    raise ArgusValidationError(
                        f"island {island.island_id!r} {field_name} must be reflected in the "
                        f"aggregate state lists: {joined}."
                    )
            for node_id in island.archive_ids:
                node = self.nodes[node_id]
                if node.node_id != self.root_id and node.island_id != island.island_id:
                    raise ArgusValidationError(
                        f"island {island.island_id!r} archive_ids contains node {node_id!r} "
                        f"owned by island {node.island_id!r}."
                    )

        for note in self.learning_notes:
            unknown_sources = [node_id for node_id in note.source_node_ids if node_id not in node_ids]
            if unknown_sources:
                joined = ", ".join(sorted(unknown_sources))
                raise ArgusValidationError(
                    "learning_notes contains source_node_ids that do not exist in nodes: "
                    f"{joined}."
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "problem_spec": self.problem_spec.to_dict(),
            "root_id": self.root_id,
            "nodes": {node_id: self.nodes[node_id].to_dict() for node_id in sorted(self.nodes)},
            "archive_ids": list(self.archive_ids),
            "frontier_ids": list(self.frontier_ids),
            "pruned_ids": list(self.pruned_ids),
            "winner_ids": list(self.winner_ids),
            "islands": {
                island_id: self.islands[island_id].to_dict()
                for island_id in sorted(self.islands)
            },
            "learning_notes": [note.to_dict() for note in self.learning_notes],
            "budget_spent": self.budget_spent,
            "step_count": self.step_count,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SearchState":
        data = _validate_payload_keys(
            payload,
            field_name="SearchState",
            required={
                "problem_spec",
                "root_id",
                "nodes",
                "archive_ids",
                "frontier_ids",
                "pruned_ids",
                "winner_ids",
                "learning_notes",
                "budget_spent",
                "step_count",
            },
            optional={"islands"},
        )

        nodes_payload = _normalize_mapping(data["nodes"], "nodes")
        nodes = {
            node_id: Node.from_dict(node_payload)
            for node_id, node_payload in sorted(nodes_payload.items())
        }
        for node_id, node in nodes.items():
            if node.node_id != node_id:
                raise ArgusValidationError(
                    f"nodes key {node_id!r} does not match embedded node_id {node.node_id!r}."
                )

        learning_payload = data["learning_notes"]
        if not _is_sequence(learning_payload):
            raise ArgusValidationError(
                f"learning_notes must be a list, got {type(learning_payload).__name__}."
            )
        learning_notes = [LearningNote.from_dict(item) for item in learning_payload]

        islands_payload = data.get("islands", {})
        islands = {
            island_id: SearchIsland.from_dict(island_payload)
            for island_id, island_payload in sorted(
                _normalize_mapping(islands_payload, "islands").items()
            )
        }

        return cls(
            problem_spec=ProblemSpec.from_dict(data["problem_spec"]),
            root_id=data["root_id"],
            nodes=nodes,
            archive_ids=data["archive_ids"],
            frontier_ids=data["frontier_ids"],
            pruned_ids=data["pruned_ids"],
            winner_ids=data["winner_ids"],
            islands=islands,
            learning_notes=learning_notes,
            budget_spent=data["budget_spent"],
            step_count=data["step_count"],
        )


@dataclass(frozen=True, slots=True)
class FinalRecommendation:
    best_bet_node_id: str
    conservative_node_id: str | None
    high_upside_node_id: str | None
    rejected_but_insightful_ids: list[str] = field(default_factory=list)
    summary_markdown: str = ""
    next_experiments: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    reversal_conditions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "best_bet_node_id",
            _normalize_non_empty_string(self.best_bet_node_id, "best_bet_node_id"),
        )
        object.__setattr__(
            self,
            "conservative_node_id",
            _normalize_optional_string(self.conservative_node_id, "conservative_node_id"),
        )
        object.__setattr__(
            self,
            "high_upside_node_id",
            _normalize_optional_string(self.high_upside_node_id, "high_upside_node_id"),
        )
        object.__setattr__(
            self,
            "rejected_but_insightful_ids",
            _normalize_unique_string_list(
                self.rejected_but_insightful_ids,
                "rejected_but_insightful_ids",
            ),
        )
        object.__setattr__(
            self,
            "summary_markdown",
            _normalize_non_empty_string(self.summary_markdown, "summary_markdown"),
        )
        object.__setattr__(
            self,
            "next_experiments",
            _normalize_string_list(self.next_experiments, "next_experiments"),
        )
        object.__setattr__(self, "assumptions", _normalize_string_list(self.assumptions, "assumptions"))
        object.__setattr__(
            self,
            "failure_modes",
            _normalize_string_list(self.failure_modes, "failure_modes"),
        )
        object.__setattr__(
            self,
            "reversal_conditions",
            _normalize_string_list(self.reversal_conditions, "reversal_conditions"),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "best_bet_node_id": self.best_bet_node_id,
            "conservative_node_id": self.conservative_node_id,
            "high_upside_node_id": self.high_upside_node_id,
            "rejected_but_insightful_ids": list(self.rejected_but_insightful_ids),
            "summary_markdown": self.summary_markdown,
            "next_experiments": list(self.next_experiments),
            "assumptions": list(self.assumptions),
            "failure_modes": list(self.failure_modes),
            "reversal_conditions": list(self.reversal_conditions),
        }
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "FinalRecommendation":
        data = _validate_payload_keys(
            payload,
            field_name="FinalRecommendation",
            required={
                "best_bet_node_id",
                "conservative_node_id",
                "high_upside_node_id",
                "rejected_but_insightful_ids",
                "summary_markdown",
                "next_experiments",
                "assumptions",
                "failure_modes",
                "reversal_conditions",
            },
        )
        return cls(
            best_bet_node_id=data["best_bet_node_id"],
            conservative_node_id=data["conservative_node_id"],
            high_upside_node_id=data["high_upside_node_id"],
            rejected_but_insightful_ids=data["rejected_but_insightful_ids"],
            summary_markdown=data["summary_markdown"],
            next_experiments=data["next_experiments"],
            assumptions=data["assumptions"],
            failure_modes=data["failure_modes"],
            reversal_conditions=data["reversal_conditions"],
        )


def _normalize_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _normalize_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_non_empty_string(value, field_name)


def _normalize_string_list(values: object, field_name: str) -> list[str]:
    if not _is_sequence(values):
        raise ArgusValidationError(
            f"{field_name} must be a list of strings, got {type(values).__name__}."
        )
    return [_normalize_non_empty_string(value, f"{field_name}[{index}]") for index, value in enumerate(values)]


def _normalize_unique_string_list(values: object, field_name: str) -> list[str]:
    normalized = _normalize_string_list(values, field_name)
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise ArgusValidationError(f"{field_name} contains duplicate values: {joined}.")
    return normalized


def _normalize_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgusValidationError(
            f"{field_name} must be an integer, got {type(value).__name__}."
        )
    if value < 0:
        raise ArgusValidationError(f"{field_name} must be non-negative, got {value}.")
    return value


def _normalize_positive_int(value: object, field_name: str) -> int:
    normalized = _normalize_non_negative_int(value, field_name)
    if normalized <= 0:
        raise ArgusValidationError(f"{field_name} must be greater than 0.")
    return normalized


def _normalize_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ArgusValidationError(
            f"{field_name} must be a finite number, got {type(value).__name__}."
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ArgusValidationError(f"{field_name} must be a finite number.")
    return normalized


def _normalize_probability(value: object, field_name: str) -> float:
    normalized = _normalize_float(value, field_name)
    if normalized < 0.0 or normalized > 1.0:
        raise ArgusValidationError(f"{field_name} must be between 0.0 and 1.0.")
    return normalized


def _normalize_enum(value: object, enum_cls: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise ArgusValidationError(
                f"{field_name} must be one of {', '.join(member.value for member in enum_cls)}."
            ) from exc
    raise ArgusValidationError(
        f"{field_name} must be a {enum_cls.__name__} or string, got {type(value).__name__}."
    )


def _normalize_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        normalized = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            normalized = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ArgusValidationError(
                f"{field_name} must be an ISO 8601 timestamp, got {value!r}."
            ) from exc
    else:
        raise ArgusValidationError(
            f"{field_name} must be a datetime or ISO 8601 string, got {type(value).__name__}."
        )

    if normalized.tzinfo is None:
        raise ArgusValidationError(f"{field_name} must include timezone information.")
    return normalized.astimezone(timezone.utc)


def _dump_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_json_object(value: object, field_name: str) -> dict[str, JSONValue]:
    mapping = _normalize_mapping(value, field_name)
    return {
        key: _normalize_json_value(item, f"{field_name}.{key}")
        for key, item in sorted(mapping.items())
    }


def _copy_json_object(value: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    return {
        key: _copy_json_value(item)
        for key, item in sorted(value.items())
    }


def _copy_json_value(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        return {key: _copy_json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_copy_json_value(item) for item in value]
    return value


def _normalize_json_value(value: object, field_name: str) -> JSONValue:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArgusValidationError(f"{field_name} must be JSON-safe and finite.")
        return value
    if isinstance(value, dict):
        return _normalize_json_object(value, field_name)
    if _is_sequence(value):
        return [_normalize_json_value(item, f"{field_name}[{index}]") for index, item in enumerate(value)]
    raise ArgusValidationError(
        f"{field_name} must be JSON-compatible, got {type(value).__name__}."
    )


def _normalize_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
    optional: set[str],
) -> Mapping[str, object]:
    data = _normalize_mapping(payload, field_name)
    keys = set(data)
    missing = sorted(required - keys)
    unexpected = sorted(keys - required - optional)
    if missing:
        raise ArgusValidationError(f"{field_name} is missing required keys: {', '.join(missing)}.")
    if unexpected:
        raise ArgusValidationError(
            f"{field_name} contains unexpected keys: {', '.join(unexpected)}."
        )
    return data


def _validate_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, object]:
    return _normalize_payload_keys(
        payload,
        field_name=field_name,
        required=required,
        optional=optional or set(),
    )


def _normalize_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ArgusValidationError(
            f"{field_name} must be an object, got {type(value).__name__}."
        )
    for key in value:
        if not isinstance(key, str):
            raise ArgusValidationError(f"{field_name} must use string keys, got {type(key).__name__}.")
    return value


def _normalize_node_map(value: object) -> dict[str, Node]:
    mapping = _normalize_mapping(value, "nodes")
    normalized: dict[str, Node] = {}
    for node_id, node in sorted(mapping.items()):
        if not isinstance(node, Node):
            raise ArgusValidationError(
                f"nodes[{node_id!r}] must be a Node instance, got {type(node).__name__}."
            )
        if node.node_id != node_id:
            raise ArgusValidationError(
                f"nodes key {node_id!r} does not match embedded node_id {node.node_id!r}."
            )
        normalized[node_id] = node
    return normalized


def _normalize_search_island_map(value: object) -> dict[str, SearchIsland]:
    mapping = _normalize_mapping(value, "islands")
    normalized: dict[str, SearchIsland] = {}
    for island_id, island in sorted(mapping.items()):
        if not isinstance(island, SearchIsland):
            raise ArgusValidationError(
                f"islands[{island_id!r}] must be a SearchIsland instance, "
                f"got {type(island).__name__}."
            )
        if island.island_id != island_id:
            raise ArgusValidationError(
                f"islands key {island_id!r} does not match embedded island_id {island.island_id!r}."
            )
        normalized[island_id] = island
    return normalized


def _normalize_sequence(value: object, field_name: str) -> list[object]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(value).__name__}."
        )
    return list(value)


def _normalize_learning_notes(value: object) -> list[LearningNote]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"learning_notes must be a list, got {type(value).__name__}."
        )
    normalized: list[LearningNote] = []
    for index, note in enumerate(value):
        if not isinstance(note, LearningNote):
            raise ArgusValidationError(
                "learning_notes entries must be LearningNote instances, "
                f"got {type(note).__name__} at index {index}."
            )
        normalized.append(note)
    return normalized


def _normalize_outcome_feedback_learning_notes(
    value: object,
    *,
    node_id: str,
) -> list[LearningNote]:
    normalized = _normalize_learning_notes(value)
    if not normalized:
        raise ArgusValidationError("learning_notes must contain at least one note.")
    for note in normalized:
        if node_id not in note.source_node_ids:
            raise ArgusValidationError(
                "Each outcome-feedback learning note must cite the referenced node_id."
            )
    return normalized


def _normalize_learning_evidence_sources(
    value: object,
    field_name: str,
) -> list[LearningEvidenceSource]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(value).__name__}."
        )
    normalized: list[LearningEvidenceSource] = []
    seen: set[LearningEvidenceSource] = set()
    for index, item in enumerate(value):
        source = _normalize_enum(item, LearningEvidenceSource, f"{field_name}[{index}]")
        if source in seen:
            continue
        seen.add(source)
        normalized.append(source)
    if not normalized:
        raise ArgusValidationError(f"{field_name} must contain at least one value.")
    return normalized


def _normalize_reusable_learning_entries(
    value: object,
    field_name: str,
) -> list[ReusableLearningNote]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(value).__name__}."
        )
    normalized: list[ReusableLearningNote] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, ReusableLearningNote):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a ReusableLearningNote instance, "
                f"got {type(entry).__name__}."
            )
        if entry.note_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate note_id values: {entry.note_id}."
            )
        seen.add(entry.note_id)
        normalized.append(entry)
    return normalized


def _normalize_outcome_feedback_entries(
    value: object,
    field_name: str,
) -> list[OutcomeFeedback]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(value).__name__}."
        )
    normalized: list[OutcomeFeedback] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, OutcomeFeedback):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be an OutcomeFeedback instance, "
                f"got {type(entry).__name__}."
            )
        if entry.feedback_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate feedback_id values: {entry.feedback_id}."
            )
        seen.add(entry.feedback_id)
        normalized.append(entry)
    return normalized


def _build_reusable_learning_note_id(
    note_type: LearningNoteType,
    text: str,
) -> str:
    normalized_type = _normalize_enum(note_type, LearningNoteType, "note_type")
    normalized_text = re.sub(r"\s+", " ", _normalize_non_empty_string(text, "text").lower())
    digest = hashlib.sha256(
        f"{normalized_type.value}\n{normalized_text}".encode("utf-8")
    ).hexdigest()[:12]
    return f"learning-{digest}"


def _merge_unique_strings(left: Sequence[str], right: Sequence[str]) -> list[str]:
    merged: list[str] = []
    for value in [*left, *right]:
        if value not in merged:
            merged.append(value)
    return merged


def _merge_unique_enums[T: StrEnum](left: Sequence[T], right: Sequence[T]) -> list[T]:
    merged: list[T] = []
    for value in [*left, *right]:
        if value not in merged:
            merged.append(value)
    return merged


def _sort_reusable_learning_entries(
    entries: Sequence[ReusableLearningNote],
) -> list[ReusableLearningNote]:
    return sorted(
        entries,
        key=lambda entry: (
            _reusable_learning_evidence_priority(entry),
            entry.observation_count,
            _reusable_learning_type_priority(entry.note_type),
            entry.last_seen_at,
            entry.note_id,
        ),
        reverse=True,
    )


def _reusable_learning_evidence_priority(entry: ReusableLearningNote) -> int:
    return (
        2
        if LearningEvidenceSource.OUTCOME_FEEDBACK in entry.evidence_sources
        else 1
    )


def _reusable_learning_type_priority(note_type: LearningNoteType) -> int:
    priorities = {
        LearningNoteType.WINNING_PATTERN: 5,
        LearningNoteType.FAILURE_PATTERN: 4,
        LearningNoteType.CONSTRAINT: 4,
        LearningNoteType.ROUTING_HINT: 3,
        LearningNoteType.SUMMARY: 2,
    }
    return priorities[note_type]


_REUSABLE_LEARNING_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "into",
    "not",
    "that",
    "the",
    "their",
    "then",
    "this",
    "with",
}


def _problem_query_tokens(problem_spec: ProblemSpec) -> set[str]:
    parts = [
        problem_spec.request,
        *problem_spec.constraints,
        *problem_spec.success_criteria,
    ]
    return _tokenize_reusable_learning_text(" ".join(parts))


def _reusable_learning_tokens(entry: ReusableLearningNote) -> set[str]:
    parts = [entry.text, *entry.problem_statements]
    return _tokenize_reusable_learning_text(" ".join(parts))


def _tokenize_reusable_learning_text(text: str) -> set[str]:
    # This lexical pass is only for retrieving a small subset of persisted notes.
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in _REUSABLE_LEARNING_STOPWORDS
    }
    return tokens


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)
