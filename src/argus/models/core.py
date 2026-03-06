from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import math

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
            optional={"score", "critique"},
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
class SearchState:
    problem_spec: ProblemSpec
    root_id: str
    nodes: dict[str, Node] = field(default_factory=dict)
    archive_ids: list[str] = field(default_factory=list)
    frontier_ids: list[str] = field(default_factory=list)
    pruned_ids: list[str] = field(default_factory=list)
    winner_ids: list[str] = field(default_factory=list)
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

        return cls(
            problem_spec=ProblemSpec.from_dict(data["problem_spec"]),
            root_id=data["root_id"],
            nodes=nodes,
            archive_ids=data["archive_ids"],
            frontier_ids=data["frontier_ids"],
            pruned_ids=data["pruned_ids"],
            winner_ids=data["winner_ids"],
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


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)
