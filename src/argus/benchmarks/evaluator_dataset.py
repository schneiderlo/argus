from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path

from argus.benchmarks.models import (
    BenchmarkFamily,
    _normalize_case_id,
    _normalize_enum,
    _normalize_non_empty_string,
    _normalize_sequence,
    _normalize_unique_string_list,
)
from argus.errors import ArgusUserError, ArgusValidationError
from argus.eval import EvaluationAssessment, NoveltyAssessment, PairwiseRankingAssessment
from argus.models import (
    ActionType,
    Candidate,
    Critique,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ScoreVector,
)

_FIXTURE_CREATED_AT = datetime(2026, 3, 6, 3, 33, 40, tzinfo=timezone.utc)


class EvaluatorBenchmarkKind(StrEnum):
    HARD_CONSTRAINT = "hard_constraint"
    NOVELTY = "novelty"
    PAIRWISE = "pairwise"
    RANKING = "ranking"


@dataclass(frozen=True, slots=True)
class ArchiveCandidateFixture:
    node_id: str
    candidate: Candidate

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _normalize_non_empty_string(self.node_id, "node_id"))
        if not isinstance(self.candidate, Candidate):
            raise ArgusValidationError(
                "candidate must be a Candidate instance, "
                f"got {type(self.candidate).__name__}."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "candidate": self.candidate.to_dict(),
        }

    def to_node(self) -> Node:
        return Node(
            node_id=self.node_id,
            parent_ids=[],
            depth=0,
            action_type=ActionType.GENERATE_SEED,
            provider_name="benchmark-fixture",
            candidate=self.candidate,
            novelty_score=0.0,
            lifecycle_status=NodeLifecycleStatus.ADMITTED,
            metadata={"fixture": "archive_candidate"},
            created_at=_FIXTURE_CREATED_AT,
        )

    @classmethod
    def from_dict(cls, payload: object) -> "ArchiveCandidateFixture":
        data = _validate_payload_keys(
            payload,
            field_name="ArchiveCandidateFixture",
            required={"node_id", "candidate"},
        )
        return cls(
            node_id=data["node_id"],
            candidate=Candidate.from_dict(data["candidate"]),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkNodeFixture:
    node_id: str
    candidate: Candidate
    score: ScoreVector
    novelty_score: float
    critique: Critique | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _normalize_non_empty_string(self.node_id, "node_id"))
        if not isinstance(self.candidate, Candidate):
            raise ArgusValidationError(
                "candidate must be a Candidate instance, "
                f"got {type(self.candidate).__name__}."
            )
        if not isinstance(self.score, ScoreVector):
            raise ArgusValidationError(
                "score must be a ScoreVector instance, "
                f"got {type(self.score).__name__}."
            )
        if self.critique is not None and not isinstance(self.critique, Critique):
            raise ArgusValidationError(
                "critique must be a Critique instance or None, "
                f"got {type(self.critique).__name__}."
            )
        object.__setattr__(
            self,
            "novelty_score",
            _normalize_probability(self.novelty_score, "novelty_score"),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "node_id": self.node_id,
            "candidate": self.candidate.to_dict(),
            "score": self.score.to_dict(),
            "novelty_score": self.novelty_score,
        }
        if self.critique is not None:
            payload["critique"] = self.critique.to_dict()
        return payload

    def to_node(self) -> Node:
        return Node(
            node_id=self.node_id,
            parent_ids=[],
            depth=0,
            action_type=ActionType.GENERATE_SEED,
            provider_name="benchmark-fixture",
            candidate=self.candidate,
            score=self.score,
            critique=self.critique,
            novelty_score=self.novelty_score,
            lifecycle_status=NodeLifecycleStatus.ADMITTED,
            metadata={"fixture": "benchmark_node"},
            created_at=_FIXTURE_CREATED_AT,
        )

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkNodeFixture":
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkNodeFixture",
            required={"node_id", "candidate", "score", "novelty_score"},
            optional={"critique"},
        )
        critique_payload = data.get("critique")
        return cls(
            node_id=data["node_id"],
            candidate=Candidate.from_dict(data["candidate"]),
            score=ScoreVector.from_dict(data["score"]),
            novelty_score=data["novelty_score"],
            critique=None if critique_payload is None else Critique.from_dict(critique_payload),
        )


@dataclass(frozen=True, slots=True)
class PairwiseObjectiveFixture:
    name: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_non_empty_string(self.name, "name"))
        object.__setattr__(
            self,
            "description",
            _normalize_non_empty_string(self.description, "description"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "PairwiseObjectiveFixture":
        data = _validate_payload_keys(
            payload,
            field_name="PairwiseObjectiveFixture",
            required={"name", "description"},
        )
        return cls(
            name=data["name"],
            description=data["description"],
        )


@dataclass(frozen=True, slots=True)
class EvaluatorBenchmarkCase:
    case_id: str
    title: str
    family: BenchmarkFamily
    kind: EvaluatorBenchmarkKind
    problem_spec: ProblemSpec
    candidate: Candidate | None = None
    archive_candidates: list[ArchiveCandidateFixture] = field(default_factory=list)
    objective: PairwiseObjectiveFixture | None = None
    left: BenchmarkNodeFixture | None = None
    right: BenchmarkNodeFixture | None = None
    nodes: list[BenchmarkNodeFixture] = field(default_factory=list)
    expected_evaluation: EvaluationAssessment | None = None
    expected_novelty: NoveltyAssessment | None = None
    expected_pairwise: PairwiseRankingAssessment | None = None
    expected_rank_order: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _normalize_case_id(self.case_id, "case_id"))
        object.__setattr__(self, "title", _normalize_non_empty_string(self.title, "title"))
        object.__setattr__(self, "family", _normalize_enum(self.family, BenchmarkFamily, "family"))
        object.__setattr__(
            self,
            "kind",
            _normalize_enum(self.kind, EvaluatorBenchmarkKind, "kind"),
        )
        if not isinstance(self.problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(self.problem_spec).__name__}."
            )
        if self.candidate is not None and not isinstance(self.candidate, Candidate):
            raise ArgusValidationError(
                "candidate must be a Candidate instance or None, "
                f"got {type(self.candidate).__name__}."
            )
        if self.objective is not None and not isinstance(self.objective, PairwiseObjectiveFixture):
            raise ArgusValidationError(
                "objective must be a PairwiseObjectiveFixture or None, "
                f"got {type(self.objective).__name__}."
            )
        if self.left is not None and not isinstance(self.left, BenchmarkNodeFixture):
            raise ArgusValidationError(
                "left must be a BenchmarkNodeFixture or None, "
                f"got {type(self.left).__name__}."
            )
        if self.right is not None and not isinstance(self.right, BenchmarkNodeFixture):
            raise ArgusValidationError(
                "right must be a BenchmarkNodeFixture or None, "
                f"got {type(self.right).__name__}."
            )
        if (
            self.expected_evaluation is not None
            and not isinstance(self.expected_evaluation, EvaluationAssessment)
        ):
            raise ArgusValidationError(
                "expected_evaluation must be an EvaluationAssessment or None, "
                f"got {type(self.expected_evaluation).__name__}."
            )
        if self.expected_novelty is not None and not isinstance(self.expected_novelty, NoveltyAssessment):
            raise ArgusValidationError(
                "expected_novelty must be a NoveltyAssessment or None, "
                f"got {type(self.expected_novelty).__name__}."
            )
        if self.expected_pairwise is not None and not isinstance(
            self.expected_pairwise,
            PairwiseRankingAssessment,
        ):
            raise ArgusValidationError(
                "expected_pairwise must be a PairwiseRankingAssessment or None, "
                f"got {type(self.expected_pairwise).__name__}."
            )
        object.__setattr__(
            self,
            "archive_candidates",
            _normalize_archive_candidates(self.archive_candidates, "archive_candidates"),
        )
        object.__setattr__(self, "nodes", _normalize_nodes(self.nodes, "nodes"))
        object.__setattr__(
            self,
            "expected_rank_order",
            _normalize_unique_string_list(self.expected_rank_order, "expected_rank_order"),
        )
        self._validate_kind_contract()

    def _validate_kind_contract(self) -> None:
        kind = self.kind
        if kind is EvaluatorBenchmarkKind.HARD_CONSTRAINT:
            if self.candidate is None or self.expected_evaluation is None:
                raise ArgusValidationError(
                    "hard_constraint cases require candidate and expected_evaluation."
                )
            if self.expected_evaluation.score.hard_constraint_pass:
                raise ArgusValidationError(
                    "hard_constraint cases must expect hard_constraint_pass=false."
                )
            _ensure_empty(self.archive_candidates, "archive_candidates", kind)
            _ensure_none(self.objective, "objective", kind)
            _ensure_none(self.left, "left", kind)
            _ensure_none(self.right, "right", kind)
            _ensure_empty(self.nodes, "nodes", kind)
            _ensure_none(self.expected_novelty, "expected_novelty", kind)
            _ensure_none(self.expected_pairwise, "expected_pairwise", kind)
            _ensure_empty(self.expected_rank_order, "expected_rank_order", kind)
            return

        if kind is EvaluatorBenchmarkKind.NOVELTY:
            if self.candidate is None or self.expected_novelty is None:
                raise ArgusValidationError("novelty cases require candidate and expected_novelty.")
            if not self.archive_candidates:
                raise ArgusValidationError("novelty cases require at least one archive candidate.")
            _ensure_none(self.objective, "objective", kind)
            _ensure_none(self.left, "left", kind)
            _ensure_none(self.right, "right", kind)
            _ensure_empty(self.nodes, "nodes", kind)
            _ensure_none(self.expected_evaluation, "expected_evaluation", kind)
            _ensure_none(self.expected_pairwise, "expected_pairwise", kind)
            _ensure_empty(self.expected_rank_order, "expected_rank_order", kind)
            return

        if kind is EvaluatorBenchmarkKind.PAIRWISE:
            if self.objective is None or self.left is None or self.right is None:
                raise ArgusValidationError(
                    "pairwise cases require objective, left, and right."
                )
            if self.left.node_id == self.right.node_id:
                raise ArgusValidationError("pairwise cases require distinct left and right node ids.")
            if self.expected_pairwise is None:
                raise ArgusValidationError("pairwise cases require expected_pairwise.")
            _ensure_none(self.candidate, "candidate", kind)
            _ensure_empty(self.archive_candidates, "archive_candidates", kind)
            _ensure_empty(self.nodes, "nodes", kind)
            _ensure_none(self.expected_evaluation, "expected_evaluation", kind)
            _ensure_none(self.expected_novelty, "expected_novelty", kind)
            _ensure_empty(self.expected_rank_order, "expected_rank_order", kind)
            return

        if kind is EvaluatorBenchmarkKind.RANKING:
            if len(self.nodes) < 2:
                raise ArgusValidationError("ranking cases require at least two nodes.")
            if not self.expected_rank_order:
                raise ArgusValidationError("ranking cases require expected_rank_order.")
            node_ids = [node.node_id for node in self.nodes]
            if sorted(node_ids) != sorted(self.expected_rank_order):
                raise ArgusValidationError(
                    "expected_rank_order must contain exactly the node ids present in nodes."
                )
            _ensure_none(self.candidate, "candidate", kind)
            _ensure_empty(self.archive_candidates, "archive_candidates", kind)
            _ensure_none(self.objective, "objective", kind)
            _ensure_none(self.left, "left", kind)
            _ensure_none(self.right, "right", kind)
            _ensure_none(self.expected_evaluation, "expected_evaluation", kind)
            _ensure_none(self.expected_novelty, "expected_novelty", kind)
            _ensure_none(self.expected_pairwise, "expected_pairwise", kind)
            return

        raise AssertionError(f"Unhandled evaluator benchmark kind: {kind}.")

    @classmethod
    def from_dict(cls, payload: object) -> "EvaluatorBenchmarkCase":
        base_data = _validate_payload_keys(
            payload,
            field_name="EvaluatorBenchmarkCase",
            required={"case_id", "title", "family", "kind", "problem_spec"},
            optional={
                "candidate",
                "archive_candidates",
                "objective",
                "left",
                "right",
                "nodes",
                "expected_assessment",
                "expected_rank_order",
            },
        )
        kind = _normalize_enum(base_data["kind"], EvaluatorBenchmarkKind, "kind")
        expected_payload = base_data.get("expected_assessment")

        candidate_payload = base_data.get("candidate")
        objective_payload = base_data.get("objective")
        left_payload = base_data.get("left")
        right_payload = base_data.get("right")
        if kind is EvaluatorBenchmarkKind.HARD_CONSTRAINT:
            expected_evaluation = None
            if expected_payload is not None:
                expected_evaluation = EvaluationAssessment.from_dict(expected_payload)
            return cls(
                case_id=base_data["case_id"],
                title=base_data["title"],
                family=base_data["family"],
                kind=kind,
                problem_spec=ProblemSpec.from_dict(base_data["problem_spec"]),
                candidate=None if candidate_payload is None else Candidate.from_dict(candidate_payload),
                expected_evaluation=expected_evaluation,
            )

        if kind is EvaluatorBenchmarkKind.NOVELTY:
            expected_novelty = None
            if expected_payload is not None:
                expected_novelty = NoveltyAssessment.from_dict(expected_payload)
            return cls(
                case_id=base_data["case_id"],
                title=base_data["title"],
                family=base_data["family"],
                kind=kind,
                problem_spec=ProblemSpec.from_dict(base_data["problem_spec"]),
                candidate=None if candidate_payload is None else Candidate.from_dict(candidate_payload),
                archive_candidates=[
                    ArchiveCandidateFixture.from_dict(item)
                    for item in _normalize_sequence(
                        base_data.get("archive_candidates", []),
                        "archive_candidates",
                    )
                ],
                expected_novelty=expected_novelty,
            )

        if kind is EvaluatorBenchmarkKind.PAIRWISE:
            expected_pairwise = None
            if expected_payload is not None:
                expected_pairwise = PairwiseRankingAssessment.from_dict(expected_payload)
            return cls(
                case_id=base_data["case_id"],
                title=base_data["title"],
                family=base_data["family"],
                kind=kind,
                problem_spec=ProblemSpec.from_dict(base_data["problem_spec"]),
                objective=(
                    None
                    if objective_payload is None
                    else PairwiseObjectiveFixture.from_dict(objective_payload)
                ),
                left=None if left_payload is None else BenchmarkNodeFixture.from_dict(left_payload),
                right=None if right_payload is None else BenchmarkNodeFixture.from_dict(right_payload),
                expected_pairwise=expected_pairwise,
            )

        if kind is EvaluatorBenchmarkKind.RANKING:
            return cls(
                case_id=base_data["case_id"],
                title=base_data["title"],
                family=base_data["family"],
                kind=kind,
                problem_spec=ProblemSpec.from_dict(base_data["problem_spec"]),
                nodes=[
                    BenchmarkNodeFixture.from_dict(item)
                    for item in _normalize_sequence(base_data.get("nodes", []), "nodes")
                ],
                expected_rank_order=base_data.get("expected_rank_order", []),
            )

        raise AssertionError(f"Unhandled evaluator benchmark kind: {kind}.")


def load_evaluator_benchmark_cases(cases_dir: Path) -> list[EvaluatorBenchmarkCase]:
    resolved_dir = cases_dir.expanduser().resolve()
    if not resolved_dir.is_dir():
        raise ArgusUserError(
            f"Evaluator benchmark cases directory does not exist: {resolved_dir}"
        )

    cases: list[EvaluatorBenchmarkCase] = []
    seen_case_ids: set[str] = set()
    for case_path in sorted(resolved_dir.glob("*.json")):
        case = _load_case_file(case_path)
        if case.case_id in seen_case_ids:
            raise ArgusValidationError(
                f"Duplicate evaluator benchmark case_id detected: {case.case_id}."
            )
        if case_path.stem != case.case_id:
            raise ArgusValidationError(
                f"Evaluator benchmark filename {case_path.name!r} does not match case_id "
                f"{case.case_id!r}."
            )
        seen_case_ids.add(case.case_id)
        cases.append(case)

    if not cases:
        raise ArgusUserError(f"No evaluator benchmark fixtures found in {resolved_dir}")
    return cases


def select_evaluator_benchmark_cases(
    cases: list[EvaluatorBenchmarkCase],
    *,
    case_name: str | None = None,
) -> list[EvaluatorBenchmarkCase]:
    if case_name is None:
        return list(cases)

    normalized_case_name = case_name.strip()
    for case in cases:
        if case.case_id == normalized_case_name:
            return [case]

    available = ", ".join(case.case_id for case in cases)
    raise ArgusUserError(
        f"Unknown evaluator benchmark case {case_name!r}. Available cases: {available}."
    )


def _load_case_file(case_path: Path) -> EvaluatorBenchmarkCase:
    try:
        payload = json.loads(case_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArgusValidationError(
            f"Evaluator benchmark case {case_path} does not contain valid JSON."
        ) from exc
    return EvaluatorBenchmarkCase.from_dict(payload)


def _normalize_archive_candidates(
    values: object,
    field_name: str,
) -> list[ArchiveCandidateFixture]:
    normalized: list[ArchiveCandidateFixture] = []
    for index, value in enumerate(_normalize_sequence(values, field_name)):
        if not isinstance(value, ArchiveCandidateFixture):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be an ArchiveCandidateFixture, "
                f"got {type(value).__name__}."
            )
        normalized.append(value)
    return normalized


def _normalize_nodes(values: object, field_name: str) -> list[BenchmarkNodeFixture]:
    normalized: list[BenchmarkNodeFixture] = []
    for index, value in enumerate(_normalize_sequence(values, field_name)):
        if not isinstance(value, BenchmarkNodeFixture):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a BenchmarkNodeFixture, "
                f"got {type(value).__name__}."
            )
        normalized.append(value)
    return normalized


def _ensure_none(value: object, field_name: str, kind: EvaluatorBenchmarkKind) -> None:
    if value is not None:
        raise ArgusValidationError(
            f"{field_name} must not be set for {kind.value} benchmark cases."
        )


def _ensure_empty(values: Sequence[object], field_name: str, kind: EvaluatorBenchmarkKind) -> None:
    if values:
        raise ArgusValidationError(
            f"{field_name} must be empty for {kind.value} benchmark cases."
        )


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
    optional: set[str] | None = None,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ArgusValidationError(
            f"{field_name} must be an object, got {type(payload).__name__}."
        )
    optional = set() if optional is None else set(optional)
    allowed = required | optional
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ArgusValidationError(
            f"{field_name} contains unexpected fields: {', '.join(unknown)}."
        )
    missing = sorted(required - set(payload))
    if missing:
        raise ArgusValidationError(
            f"{field_name} is missing required fields: {', '.join(missing)}."
        )
    return dict(payload)
