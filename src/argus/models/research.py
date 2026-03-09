from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from argus.errors import ArgusValidationError
from argus.models.core import (
    Candidate,
    _dump_datetime,
    _normalize_datetime,
    _normalize_enum,
    _normalize_float,
    _normalize_mapping,
    _normalize_non_empty_string,
    _normalize_optional_string,
    _normalize_probability,
    _normalize_sequence,
    _normalize_string_list,
    _normalize_unique_string_list,
    _validate_payload_keys,
)


class CoverageStatus(StrEnum):
    UNEXPLORED = "unexplored"
    SEEDED = "seeded"
    TRIAGED = "triaged"
    DEEPENED = "deepened"
    REDTEAMED = "redteamed"
    CLOSED = "closed"
    DOMINATED = "dominated"


class ProposalDisposition(StrEnum):
    SURVIVE = "survive"
    ELIMINATE = "eliminate"
    COLLAPSE = "collapse"


class HybridVerdict(StrEnum):
    PURSUE = "pursue"
    HOLD = "hold"
    REJECT = "reject"


class ResearchSchedulerAction(StrEnum):
    EXPAND = "expand"
    DEEPEN = "deepen"
    REDTEAM = "redteam"
    HYBRIDIZE = "hybridize"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class SearchAxis:
    axis_id: str
    label: str
    description: str
    options: list[str]
    rationale: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis_id", _normalize_non_empty_string(self.axis_id, "axis_id"))
        object.__setattr__(self, "label", _normalize_non_empty_string(self.label, "label"))
        object.__setattr__(
            self,
            "description",
            _normalize_non_empty_string(self.description, "description"),
        )
        object.__setattr__(self, "options", _normalize_unique_string_list(self.options, "options"))
        object.__setattr__(self, "rationale", _normalize_optional_string(self.rationale, "rationale"))
        if len(self.options) < 2:
            raise ArgusValidationError("options must contain at least two distinct values.")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "axis_id": self.axis_id,
            "label": self.label,
            "description": self.description,
            "options": list(self.options),
        }
        if self.rationale is not None:
            payload["rationale"] = self.rationale
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "SearchAxis":
        data = _validate_payload_keys(
            payload,
            field_name="SearchAxis",
            required={"axis_id", "label", "description", "options"},
            optional={"rationale"},
        )
        return cls(
            axis_id=data["axis_id"],
            label=data["label"],
            description=data["description"],
            options=data["options"],
            rationale=data.get("rationale"),
        )


@dataclass(frozen=True, slots=True)
class SearchCell:
    cell_id: str
    label: str
    axis_assignments: dict[str, str]
    hypothesis: str
    coverage_status: CoverageStatus = CoverageStatus.UNEXPLORED
    uncertainty: float = 1.0
    hard_gate_risk: float = 0.0
    evidence_strength: float = 0.0
    incumbent_proposal_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_id", _normalize_non_empty_string(self.cell_id, "cell_id"))
        object.__setattr__(self, "label", _normalize_non_empty_string(self.label, "label"))
        object.__setattr__(
            self,
            "axis_assignments",
            _normalize_string_mapping(self.axis_assignments, "axis_assignments"),
        )
        object.__setattr__(
            self,
            "hypothesis",
            _normalize_non_empty_string(self.hypothesis, "hypothesis"),
        )
        object.__setattr__(
            self,
            "coverage_status",
            _normalize_enum(self.coverage_status, CoverageStatus, "coverage_status"),
        )
        object.__setattr__(self, "uncertainty", _normalize_probability(self.uncertainty, "uncertainty"))
        object.__setattr__(
            self,
            "hard_gate_risk",
            _normalize_probability(self.hard_gate_risk, "hard_gate_risk"),
        )
        object.__setattr__(
            self,
            "evidence_strength",
            _normalize_probability(self.evidence_strength, "evidence_strength"),
        )
        object.__setattr__(
            self,
            "incumbent_proposal_ids",
            _normalize_unique_string_list(self.incumbent_proposal_ids, "incumbent_proposal_ids"),
        )
        object.__setattr__(self, "notes", _normalize_string_list(self.notes, "notes"))
        if not self.axis_assignments:
            raise ArgusValidationError("axis_assignments must contain at least one axis choice.")

    def to_dict(self) -> dict[str, object]:
        return {
            "cell_id": self.cell_id,
            "label": self.label,
            "axis_assignments": dict(sorted(self.axis_assignments.items())),
            "hypothesis": self.hypothesis,
            "coverage_status": self.coverage_status.value,
            "uncertainty": self.uncertainty,
            "hard_gate_risk": self.hard_gate_risk,
            "evidence_strength": self.evidence_strength,
            "incumbent_proposal_ids": list(self.incumbent_proposal_ids),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SearchCell":
        data = _validate_payload_keys(
            payload,
            field_name="SearchCell",
            required={
                "cell_id",
                "label",
                "axis_assignments",
                "hypothesis",
                "coverage_status",
                "uncertainty",
                "hard_gate_risk",
                "evidence_strength",
                "incumbent_proposal_ids",
                "notes",
            },
        )
        return cls(
            cell_id=data["cell_id"],
            label=data["label"],
            axis_assignments=dict(data["axis_assignments"]),
            hypothesis=data["hypothesis"],
            coverage_status=data["coverage_status"],
            uncertainty=data["uncertainty"],
            hard_gate_risk=data["hard_gate_risk"],
            evidence_strength=data["evidence_strength"],
            incumbent_proposal_ids=data["incumbent_proposal_ids"],
            notes=data["notes"],
        )


@dataclass(frozen=True, slots=True)
class SearchSpaceFrame:
    frame_id: str
    problem_statement: str
    target_decision: str
    hard_gates: list[str]
    soft_criteria: list[str]
    baseline_options: list[str]
    axes: list[SearchAxis]
    coverage_plan: list[str]
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _normalize_non_empty_string(self.frame_id, "frame_id"))
        object.__setattr__(
            self,
            "problem_statement",
            _normalize_non_empty_string(self.problem_statement, "problem_statement"),
        )
        object.__setattr__(
            self,
            "target_decision",
            _normalize_non_empty_string(self.target_decision, "target_decision"),
        )
        object.__setattr__(self, "hard_gates", _normalize_string_list(self.hard_gates, "hard_gates"))
        object.__setattr__(
            self,
            "soft_criteria",
            _normalize_string_list(self.soft_criteria, "soft_criteria"),
        )
        object.__setattr__(
            self,
            "baseline_options",
            _normalize_string_list(self.baseline_options, "baseline_options"),
        )
        object.__setattr__(self, "axes", _normalize_axes(self.axes, "axes"))
        object.__setattr__(
            self,
            "coverage_plan",
            _normalize_string_list(self.coverage_plan, "coverage_plan"),
        )
        object.__setattr__(self, "notes", _normalize_string_list(self.notes, "notes"))
        if not self.axes:
            raise ArgusValidationError("axes must contain at least one search axis.")

    def to_dict(self) -> dict[str, object]:
        return {
            "frame_id": self.frame_id,
            "problem_statement": self.problem_statement,
            "target_decision": self.target_decision,
            "hard_gates": list(self.hard_gates),
            "soft_criteria": list(self.soft_criteria),
            "baseline_options": list(self.baseline_options),
            "axes": [axis.to_dict() for axis in self.axes],
            "coverage_plan": list(self.coverage_plan),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SearchSpaceFrame":
        data = _validate_payload_keys(
            payload,
            field_name="SearchSpaceFrame",
            required={
                "frame_id",
                "problem_statement",
                "target_decision",
                "hard_gates",
                "soft_criteria",
                "baseline_options",
                "axes",
                "coverage_plan",
                "notes",
            },
        )
        return cls(
            frame_id=data["frame_id"],
            problem_statement=data["problem_statement"],
            target_decision=data["target_decision"],
            hard_gates=data["hard_gates"],
            soft_criteria=data["soft_criteria"],
            baseline_options=data["baseline_options"],
            axes=[SearchAxis.from_dict(item) for item in _normalize_sequence(data["axes"], "axes")],
            coverage_plan=data["coverage_plan"],
            notes=data["notes"],
        )


@dataclass(frozen=True, slots=True)
class CoverageLedger:
    ledger_id: str
    frame_id: str
    cells: list[SearchCell]
    coverage_summary: str
    next_questions: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "ledger_id", _normalize_non_empty_string(self.ledger_id, "ledger_id"))
        object.__setattr__(self, "frame_id", _normalize_non_empty_string(self.frame_id, "frame_id"))
        object.__setattr__(self, "cells", _normalize_cells(self.cells, "cells"))
        object.__setattr__(
            self,
            "coverage_summary",
            _normalize_non_empty_string(self.coverage_summary, "coverage_summary"),
        )
        object.__setattr__(
            self,
            "next_questions",
            _normalize_string_list(self.next_questions, "next_questions"),
        )
        object.__setattr__(self, "updated_at", _normalize_datetime(self.updated_at, "updated_at"))
        if not self.cells:
            raise ArgusValidationError("cells must contain at least one search cell.")

    def to_dict(self) -> dict[str, object]:
        return {
            "ledger_id": self.ledger_id,
            "frame_id": self.frame_id,
            "cells": [cell.to_dict() for cell in self.cells],
            "coverage_summary": self.coverage_summary,
            "next_questions": list(self.next_questions),
            "updated_at": _dump_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "CoverageLedger":
        data = _validate_payload_keys(
            payload,
            field_name="CoverageLedger",
            required={
                "ledger_id",
                "frame_id",
                "cells",
                "coverage_summary",
                "next_questions",
                "updated_at",
            },
        )
        return cls(
            ledger_id=data["ledger_id"],
            frame_id=data["frame_id"],
            cells=[SearchCell.from_dict(item) for item in _normalize_sequence(data["cells"], "cells")],
            coverage_summary=data["coverage_summary"],
            next_questions=data["next_questions"],
            updated_at=data["updated_at"],
        )


@dataclass(frozen=True, slots=True)
class ProposalBrief:
    proposal_id: str
    cell_id: str
    title: str
    summary: str
    candidate: Candidate
    seed_rationale: str
    open_questions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    parent_node_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_id",
            _normalize_non_empty_string(self.proposal_id, "proposal_id"),
        )
        object.__setattr__(self, "cell_id", _normalize_non_empty_string(self.cell_id, "cell_id"))
        object.__setattr__(self, "title", _normalize_non_empty_string(self.title, "title"))
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        if not isinstance(self.candidate, Candidate):
            raise ArgusValidationError(
                f"candidate must be a Candidate instance, got {type(self.candidate).__name__}."
            )
        object.__setattr__(
            self,
            "seed_rationale",
            _normalize_non_empty_string(self.seed_rationale, "seed_rationale"),
        )
        object.__setattr__(
            self,
            "open_questions",
            _normalize_string_list(self.open_questions, "open_questions"),
        )
        object.__setattr__(self, "evidence", _normalize_string_list(self.evidence, "evidence"))
        object.__setattr__(
            self,
            "parent_node_ids",
            _normalize_unique_string_list(self.parent_node_ids, "parent_node_ids"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "cell_id": self.cell_id,
            "title": self.title,
            "summary": self.summary,
            "candidate": self.candidate.to_dict(),
            "seed_rationale": self.seed_rationale,
            "open_questions": list(self.open_questions),
            "evidence": list(self.evidence),
            "parent_node_ids": list(self.parent_node_ids),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ProposalBrief":
        data = _validate_payload_keys(
            payload,
            field_name="ProposalBrief",
            required={
                "proposal_id",
                "cell_id",
                "title",
                "summary",
                "candidate",
                "seed_rationale",
                "open_questions",
                "evidence",
                "parent_node_ids",
            },
        )
        return cls(
            proposal_id=data["proposal_id"],
            cell_id=data["cell_id"],
            title=data["title"],
            summary=data["summary"],
            candidate=Candidate.from_dict(data["candidate"]),
            seed_rationale=data["seed_rationale"],
            open_questions=data["open_questions"],
            evidence=data["evidence"],
            parent_node_ids=data["parent_node_ids"],
        )


@dataclass(frozen=True, slots=True)
class ProposalTriageDecision:
    proposal_id: str
    disposition: ProposalDisposition
    rationale: str
    merged_into_proposal_id: str | None = None
    follow_up: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_id",
            _normalize_non_empty_string(self.proposal_id, "proposal_id"),
        )
        object.__setattr__(
            self,
            "disposition",
            _normalize_enum(self.disposition, ProposalDisposition, "disposition"),
        )
        object.__setattr__(self, "rationale", _normalize_non_empty_string(self.rationale, "rationale"))
        object.__setattr__(
            self,
            "merged_into_proposal_id",
            _normalize_optional_string(self.merged_into_proposal_id, "merged_into_proposal_id"),
        )
        object.__setattr__(self, "follow_up", _normalize_optional_string(self.follow_up, "follow_up"))
        if self.disposition is ProposalDisposition.COLLAPSE and self.merged_into_proposal_id is None:
            raise ArgusValidationError(
                "merged_into_proposal_id must be set when disposition is collapse."
            )
        if self.disposition is not ProposalDisposition.COLLAPSE and self.merged_into_proposal_id is not None:
            raise ArgusValidationError(
                "merged_into_proposal_id is only valid when disposition is collapse."
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "proposal_id": self.proposal_id,
            "disposition": self.disposition.value,
            "rationale": self.rationale,
        }
        if self.merged_into_proposal_id is not None:
            payload["merged_into_proposal_id"] = self.merged_into_proposal_id
        if self.follow_up is not None:
            payload["follow_up"] = self.follow_up
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "ProposalTriageDecision":
        data = _validate_payload_keys(
            payload,
            field_name="ProposalTriageDecision",
            required={"proposal_id", "disposition", "rationale"},
            optional={"merged_into_proposal_id", "follow_up"},
        )
        return cls(
            proposal_id=data["proposal_id"],
            disposition=data["disposition"],
            rationale=data["rationale"],
            merged_into_proposal_id=data.get("merged_into_proposal_id"),
            follow_up=data.get("follow_up"),
        )


@dataclass(frozen=True, slots=True)
class TriageReport:
    report_id: str
    frame_id: str
    decisions: list[ProposalTriageDecision]
    survivor_ids: list[str]
    unexplored_cell_ids: list[str]
    summary: str
    next_actions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", _normalize_non_empty_string(self.report_id, "report_id"))
        object.__setattr__(self, "frame_id", _normalize_non_empty_string(self.frame_id, "frame_id"))
        object.__setattr__(self, "decisions", _normalize_triage_decisions(self.decisions, "decisions"))
        object.__setattr__(
            self,
            "survivor_ids",
            _normalize_unique_string_list(self.survivor_ids, "survivor_ids"),
        )
        object.__setattr__(
            self,
            "unexplored_cell_ids",
            _normalize_unique_string_list(self.unexplored_cell_ids, "unexplored_cell_ids"),
        )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(self, "next_actions", _normalize_string_list(self.next_actions, "next_actions"))

        survivor_set = {
            decision.proposal_id
            for decision in self.decisions
            if decision.disposition is ProposalDisposition.SURVIVE
        }
        if set(self.survivor_ids) != survivor_set:
            raise ArgusValidationError(
                "survivor_ids must match the proposals marked as survive in decisions."
            )

        decision_ids = {decision.proposal_id for decision in self.decisions}
        for decision in self.decisions:
            merged_into = decision.merged_into_proposal_id
            if merged_into is not None and merged_into not in decision_ids:
                raise ArgusValidationError(
                    "merged_into_proposal_id must reference another proposal in decisions."
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "frame_id": self.frame_id,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "survivor_ids": list(self.survivor_ids),
            "unexplored_cell_ids": list(self.unexplored_cell_ids),
            "summary": self.summary,
            "next_actions": list(self.next_actions),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "TriageReport":
        data = _validate_payload_keys(
            payload,
            field_name="TriageReport",
            required={
                "report_id",
                "frame_id",
                "decisions",
                "survivor_ids",
                "unexplored_cell_ids",
                "summary",
                "next_actions",
            },
        )
        return cls(
            report_id=data["report_id"],
            frame_id=data["frame_id"],
            decisions=[
                ProposalTriageDecision.from_dict(item)
                for item in _normalize_sequence(data["decisions"], "decisions")
            ],
            survivor_ids=data["survivor_ids"],
            unexplored_cell_ids=data["unexplored_cell_ids"],
            summary=data["summary"],
            next_actions=data["next_actions"],
        )


@dataclass(frozen=True, slots=True)
class DeepDiveDoc:
    doc_id: str
    proposal_id: str
    title: str
    executive_summary: str
    detailed_mechanism: str
    implementation_plan: list[str]
    key_unknowns: list[str]
    supporting_evidence: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "doc_id", _normalize_non_empty_string(self.doc_id, "doc_id"))
        object.__setattr__(
            self,
            "proposal_id",
            _normalize_non_empty_string(self.proposal_id, "proposal_id"),
        )
        object.__setattr__(self, "title", _normalize_non_empty_string(self.title, "title"))
        object.__setattr__(
            self,
            "executive_summary",
            _normalize_non_empty_string(self.executive_summary, "executive_summary"),
        )
        object.__setattr__(
            self,
            "detailed_mechanism",
            _normalize_non_empty_string(self.detailed_mechanism, "detailed_mechanism"),
        )
        object.__setattr__(
            self,
            "implementation_plan",
            _normalize_string_list(self.implementation_plan, "implementation_plan"),
        )
        object.__setattr__(
            self,
            "key_unknowns",
            _normalize_string_list(self.key_unknowns, "key_unknowns"),
        )
        object.__setattr__(
            self,
            "supporting_evidence",
            _normalize_string_list(self.supporting_evidence, "supporting_evidence"),
        )
        object.__setattr__(self, "assumptions", _normalize_string_list(self.assumptions, "assumptions"))

    def to_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "proposal_id": self.proposal_id,
            "title": self.title,
            "executive_summary": self.executive_summary,
            "detailed_mechanism": self.detailed_mechanism,
            "implementation_plan": list(self.implementation_plan),
            "key_unknowns": list(self.key_unknowns),
            "supporting_evidence": list(self.supporting_evidence),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "DeepDiveDoc":
        data = _validate_payload_keys(
            payload,
            field_name="DeepDiveDoc",
            required={
                "doc_id",
                "proposal_id",
                "title",
                "executive_summary",
                "detailed_mechanism",
                "implementation_plan",
                "key_unknowns",
                "supporting_evidence",
                "assumptions",
            },
        )
        return cls(
            doc_id=data["doc_id"],
            proposal_id=data["proposal_id"],
            title=data["title"],
            executive_summary=data["executive_summary"],
            detailed_mechanism=data["detailed_mechanism"],
            implementation_plan=data["implementation_plan"],
            key_unknowns=data["key_unknowns"],
            supporting_evidence=data["supporting_evidence"],
            assumptions=data["assumptions"],
        )


@dataclass(frozen=True, slots=True)
class AdversarialReview:
    review_id: str
    proposal_id: str
    thesis_under_test: str
    hidden_dependencies: list[str]
    failure_modes: list[str]
    mitigations: list[str]
    summary: str
    verdict: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_id", _normalize_non_empty_string(self.review_id, "review_id"))
        object.__setattr__(
            self,
            "proposal_id",
            _normalize_non_empty_string(self.proposal_id, "proposal_id"),
        )
        object.__setattr__(
            self,
            "thesis_under_test",
            _normalize_non_empty_string(self.thesis_under_test, "thesis_under_test"),
        )
        object.__setattr__(
            self,
            "hidden_dependencies",
            _normalize_string_list(self.hidden_dependencies, "hidden_dependencies"),
        )
        object.__setattr__(
            self,
            "failure_modes",
            _normalize_string_list(self.failure_modes, "failure_modes"),
        )
        object.__setattr__(self, "mitigations", _normalize_string_list(self.mitigations, "mitigations"))
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(self, "verdict", _normalize_non_empty_string(self.verdict, "verdict"))
        object.__setattr__(self, "confidence", _normalize_probability(self.confidence, "confidence"))
        object.__setattr__(self, "evidence", _normalize_string_list(self.evidence, "evidence"))

    def to_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "proposal_id": self.proposal_id,
            "thesis_under_test": self.thesis_under_test,
            "hidden_dependencies": list(self.hidden_dependencies),
            "failure_modes": list(self.failure_modes),
            "mitigations": list(self.mitigations),
            "summary": self.summary,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "AdversarialReview":
        data = _validate_payload_keys(
            payload,
            field_name="AdversarialReview",
            required={
                "review_id",
                "proposal_id",
                "thesis_under_test",
                "hidden_dependencies",
                "failure_modes",
                "mitigations",
                "summary",
                "verdict",
                "confidence",
                "evidence",
            },
        )
        return cls(
            review_id=data["review_id"],
            proposal_id=data["proposal_id"],
            thesis_under_test=data["thesis_under_test"],
            hidden_dependencies=data["hidden_dependencies"],
            failure_modes=data["failure_modes"],
            mitigations=data["mitigations"],
            summary=data["summary"],
            verdict=data["verdict"],
            confidence=data["confidence"],
            evidence=data["evidence"],
        )


@dataclass(frozen=True, slots=True)
class ComparisonMatrixRow:
    proposal_id: str
    criterion_scores: dict[str, float]
    advantages: list[str]
    liabilities: list[str]
    takeaway: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_id",
            _normalize_non_empty_string(self.proposal_id, "proposal_id"),
        )
        object.__setattr__(
            self,
            "criterion_scores",
            _normalize_float_mapping(self.criterion_scores, "criterion_scores"),
        )
        object.__setattr__(self, "advantages", _normalize_string_list(self.advantages, "advantages"))
        object.__setattr__(self, "liabilities", _normalize_string_list(self.liabilities, "liabilities"))
        object.__setattr__(self, "takeaway", _normalize_non_empty_string(self.takeaway, "takeaway"))
        if not self.criterion_scores:
            raise ArgusValidationError("criterion_scores must contain at least one criterion.")

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "criterion_scores": dict(sorted(self.criterion_scores.items())),
            "advantages": list(self.advantages),
            "liabilities": list(self.liabilities),
            "takeaway": self.takeaway,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ComparisonMatrixRow":
        data = _validate_payload_keys(
            payload,
            field_name="ComparisonMatrixRow",
            required={
                "proposal_id",
                "criterion_scores",
                "advantages",
                "liabilities",
                "takeaway",
            },
        )
        return cls(
            proposal_id=data["proposal_id"],
            criterion_scores=dict(data["criterion_scores"]),
            advantages=data["advantages"],
            liabilities=data["liabilities"],
            takeaway=data["takeaway"],
        )


@dataclass(frozen=True, slots=True)
class ComparisonMatrix:
    matrix_id: str
    frame_id: str
    criteria: list[str]
    rows: list[ComparisonMatrixRow]
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "matrix_id", _normalize_non_empty_string(self.matrix_id, "matrix_id"))
        object.__setattr__(self, "frame_id", _normalize_non_empty_string(self.frame_id, "frame_id"))
        object.__setattr__(self, "criteria", _normalize_unique_string_list(self.criteria, "criteria"))
        object.__setattr__(self, "rows", _normalize_matrix_rows(self.rows, "rows"))
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        if not self.criteria:
            raise ArgusValidationError("criteria must contain at least one criterion.")

        expected = set(self.criteria)
        for row in self.rows:
            if set(row.criterion_scores) != expected:
                raise ArgusValidationError(
                    "Each comparison row must score every criterion exactly once."
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "matrix_id": self.matrix_id,
            "frame_id": self.frame_id,
            "criteria": list(self.criteria),
            "rows": [row.to_dict() for row in self.rows],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ComparisonMatrix":
        data = _validate_payload_keys(
            payload,
            field_name="ComparisonMatrix",
            required={"matrix_id", "frame_id", "criteria", "rows", "summary"},
        )
        return cls(
            matrix_id=data["matrix_id"],
            frame_id=data["frame_id"],
            criteria=data["criteria"],
            rows=[ComparisonMatrixRow.from_dict(item) for item in _normalize_sequence(data["rows"], "rows")],
            summary=data["summary"],
        )


@dataclass(frozen=True, slots=True)
class HybridAssessment:
    assessment_id: str
    source_proposal_ids: list[str]
    hybrid_name: str
    seam_hypothesis: str
    repaired_failure_mode: str
    complementary_strengths: list[str]
    complexity_tax: str
    expected_upside: str
    open_questions: list[str]
    verdict: HybridVerdict
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assessment_id",
            _normalize_non_empty_string(self.assessment_id, "assessment_id"),
        )
        object.__setattr__(
            self,
            "source_proposal_ids",
            _normalize_unique_string_list(self.source_proposal_ids, "source_proposal_ids"),
        )
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
        object.__setattr__(self, "verdict", _normalize_enum(self.verdict, HybridVerdict, "verdict"))
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        if len(self.source_proposal_ids) < 2:
            raise ArgusValidationError(
                "source_proposal_ids must contain at least two distinct proposals."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "source_proposal_ids": list(self.source_proposal_ids),
            "hybrid_name": self.hybrid_name,
            "seam_hypothesis": self.seam_hypothesis,
            "repaired_failure_mode": self.repaired_failure_mode,
            "complementary_strengths": list(self.complementary_strengths),
            "complexity_tax": self.complexity_tax,
            "expected_upside": self.expected_upside,
            "open_questions": list(self.open_questions),
            "verdict": self.verdict.value,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "HybridAssessment":
        data = _validate_payload_keys(
            payload,
            field_name="HybridAssessment",
            required={
                "assessment_id",
                "source_proposal_ids",
                "hybrid_name",
                "seam_hypothesis",
                "repaired_failure_mode",
                "complementary_strengths",
                "complexity_tax",
                "expected_upside",
                "open_questions",
                "verdict",
                "summary",
            },
        )
        return cls(
            assessment_id=data["assessment_id"],
            source_proposal_ids=data["source_proposal_ids"],
            hybrid_name=data["hybrid_name"],
            seam_hypothesis=data["seam_hypothesis"],
            repaired_failure_mode=data["repaired_failure_mode"],
            complementary_strengths=data["complementary_strengths"],
            complexity_tax=data["complexity_tax"],
            expected_upside=data["expected_upside"],
            open_questions=data["open_questions"],
            verdict=data["verdict"],
            summary=data["summary"],
        )


@dataclass(frozen=True, slots=True)
class FinalDecisionDoc:
    decision_id: str
    frame_id: str
    selected_proposal_id: str
    runner_up_proposal_id: str | None
    conservative_proposal_id: str | None
    high_upside_proposal_id: str | None
    summary: str
    decision_rule: str
    assumptions: list[str]
    top_risks: list[str]
    mitigations: list[str]
    first_spike: list[str]
    kill_criteria: list[str]
    next_experiments: list[str]
    reversal_conditions: list[str]
    rejected_proposal_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _normalize_non_empty_string(self.decision_id, "decision_id"),
        )
        object.__setattr__(self, "frame_id", _normalize_non_empty_string(self.frame_id, "frame_id"))
        object.__setattr__(
            self,
            "selected_proposal_id",
            _normalize_non_empty_string(self.selected_proposal_id, "selected_proposal_id"),
        )
        object.__setattr__(
            self,
            "runner_up_proposal_id",
            _normalize_optional_string(self.runner_up_proposal_id, "runner_up_proposal_id"),
        )
        object.__setattr__(
            self,
            "conservative_proposal_id",
            _normalize_optional_string(self.conservative_proposal_id, "conservative_proposal_id"),
        )
        object.__setattr__(
            self,
            "high_upside_proposal_id",
            _normalize_optional_string(self.high_upside_proposal_id, "high_upside_proposal_id"),
        )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(
            self,
            "decision_rule",
            _normalize_non_empty_string(self.decision_rule, "decision_rule"),
        )
        object.__setattr__(self, "assumptions", _normalize_string_list(self.assumptions, "assumptions"))
        object.__setattr__(self, "top_risks", _normalize_string_list(self.top_risks, "top_risks"))
        object.__setattr__(self, "mitigations", _normalize_string_list(self.mitigations, "mitigations"))
        object.__setattr__(self, "first_spike", _normalize_string_list(self.first_spike, "first_spike"))
        object.__setattr__(
            self,
            "kill_criteria",
            _normalize_string_list(self.kill_criteria, "kill_criteria"),
        )
        object.__setattr__(
            self,
            "next_experiments",
            _normalize_string_list(self.next_experiments, "next_experiments"),
        )
        object.__setattr__(
            self,
            "reversal_conditions",
            _normalize_string_list(self.reversal_conditions, "reversal_conditions"),
        )
        object.__setattr__(
            self,
            "rejected_proposal_ids",
            _normalize_unique_string_list(self.rejected_proposal_ids, "rejected_proposal_ids"),
        )
        if self.runner_up_proposal_id == self.selected_proposal_id:
            raise ArgusValidationError("runner_up_proposal_id must differ from selected_proposal_id.")
        if self.selected_proposal_id in self.rejected_proposal_ids:
            raise ArgusValidationError("selected_proposal_id must not appear in rejected_proposal_ids.")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "decision_id": self.decision_id,
            "frame_id": self.frame_id,
            "selected_proposal_id": self.selected_proposal_id,
            "summary": self.summary,
            "decision_rule": self.decision_rule,
            "assumptions": list(self.assumptions),
            "top_risks": list(self.top_risks),
            "mitigations": list(self.mitigations),
            "first_spike": list(self.first_spike),
            "kill_criteria": list(self.kill_criteria),
            "next_experiments": list(self.next_experiments),
            "reversal_conditions": list(self.reversal_conditions),
            "rejected_proposal_ids": list(self.rejected_proposal_ids),
        }
        if self.runner_up_proposal_id is not None:
            payload["runner_up_proposal_id"] = self.runner_up_proposal_id
        if self.conservative_proposal_id is not None:
            payload["conservative_proposal_id"] = self.conservative_proposal_id
        if self.high_upside_proposal_id is not None:
            payload["high_upside_proposal_id"] = self.high_upside_proposal_id
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "FinalDecisionDoc":
        data = _validate_payload_keys(
            payload,
            field_name="FinalDecisionDoc",
            required={
                "decision_id",
                "frame_id",
                "selected_proposal_id",
                "summary",
                "decision_rule",
                "assumptions",
                "top_risks",
                "mitigations",
                "first_spike",
                "kill_criteria",
                "next_experiments",
                "reversal_conditions",
                "rejected_proposal_ids",
            },
            optional={
                "runner_up_proposal_id",
                "conservative_proposal_id",
                "high_upside_proposal_id",
            },
        )
        return cls(
            decision_id=data["decision_id"],
            frame_id=data["frame_id"],
            selected_proposal_id=data["selected_proposal_id"],
            runner_up_proposal_id=data.get("runner_up_proposal_id"),
            conservative_proposal_id=data.get("conservative_proposal_id"),
            high_upside_proposal_id=data.get("high_upside_proposal_id"),
            summary=data["summary"],
            decision_rule=data["decision_rule"],
            assumptions=data["assumptions"],
            top_risks=data["top_risks"],
            mitigations=data["mitigations"],
            first_spike=data["first_spike"],
            kill_criteria=data["kill_criteria"],
            next_experiments=data["next_experiments"],
            reversal_conditions=data["reversal_conditions"],
            rejected_proposal_ids=data["rejected_proposal_ids"],
        )


@dataclass(frozen=True, slots=True)
class SchedulerDecision:
    decision_id: str
    action: ResearchSchedulerAction
    rationale: str
    remaining_budget: int
    priority_score: float
    target_cell_ids: list[str] = field(default_factory=list)
    target_proposal_ids: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    selected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _normalize_non_empty_string(self.decision_id, "decision_id"),
        )
        object.__setattr__(
            self,
            "action",
            _normalize_enum(self.action, ResearchSchedulerAction, "action"),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_non_empty_string(self.rationale, "rationale"),
        )
        if not isinstance(self.remaining_budget, int) or self.remaining_budget < 0:
            raise ArgusValidationError("remaining_budget must be an integer >= 0.")
        object.__setattr__(
            self,
            "priority_score",
            _normalize_probability(self.priority_score, "priority_score"),
        )
        object.__setattr__(
            self,
            "target_cell_ids",
            _normalize_unique_string_list(self.target_cell_ids, "target_cell_ids"),
        )
        object.__setattr__(
            self,
            "target_proposal_ids",
            _normalize_unique_string_list(self.target_proposal_ids, "target_proposal_ids"),
        )
        object.__setattr__(self, "signals", _normalize_string_list(self.signals, "signals"))
        object.__setattr__(self, "selected_at", _normalize_datetime(self.selected_at, "selected_at"))

        if self.action is ResearchSchedulerAction.EXPAND and not self.target_cell_ids:
            raise ArgusValidationError("expand decisions must target at least one cell.")
        if self.action is ResearchSchedulerAction.DEEPEN and not self.target_proposal_ids:
            raise ArgusValidationError("deepen decisions must target at least one proposal.")
        if self.action is ResearchSchedulerAction.REDTEAM and not self.target_proposal_ids:
            raise ArgusValidationError("redteam decisions must target at least one proposal.")
        if self.action is ResearchSchedulerAction.HYBRIDIZE and len(self.target_proposal_ids) < 2:
            raise ArgusValidationError("hybridize decisions must target at least two proposals.")
        if self.action is ResearchSchedulerAction.STOP:
            if self.target_cell_ids or self.target_proposal_ids:
                raise ArgusValidationError("stop decisions must not target cells or proposals.")

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_id": self.decision_id,
            "action": self.action.value,
            "rationale": self.rationale,
            "remaining_budget": self.remaining_budget,
            "priority_score": self.priority_score,
            "target_cell_ids": list(self.target_cell_ids),
            "target_proposal_ids": list(self.target_proposal_ids),
            "signals": list(self.signals),
            "selected_at": _dump_datetime(self.selected_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SchedulerDecision":
        data = _validate_payload_keys(
            payload,
            field_name="SchedulerDecision",
            required={
                "decision_id",
                "action",
                "rationale",
                "remaining_budget",
                "priority_score",
                "target_cell_ids",
                "target_proposal_ids",
                "signals",
                "selected_at",
            },
        )
        return cls(
            decision_id=data["decision_id"],
            action=data["action"],
            rationale=data["rationale"],
            remaining_budget=data["remaining_budget"],
            priority_score=data["priority_score"],
            target_cell_ids=data["target_cell_ids"],
            target_proposal_ids=data["target_proposal_ids"],
            signals=data["signals"],
            selected_at=data["selected_at"],
        )


@dataclass(frozen=True, slots=True)
class ResearchArtifactBundle:
    search_space_frame: SearchSpaceFrame | None = None
    coverage_ledger: CoverageLedger | None = None
    scheduler_decisions: list[SchedulerDecision] = field(default_factory=list)
    proposal_briefs: list[ProposalBrief] = field(default_factory=list)
    triage_reports: list[TriageReport] = field(default_factory=list)
    deep_dive_docs: list[DeepDiveDoc] = field(default_factory=list)
    adversarial_reviews: list[AdversarialReview] = field(default_factory=list)
    comparison_matrices: list[ComparisonMatrix] = field(default_factory=list)
    hybrid_assessments: list[HybridAssessment] = field(default_factory=list)
    final_decision_doc: FinalDecisionDoc | None = None

    def __post_init__(self) -> None:
        if self.search_space_frame is not None and not isinstance(self.search_space_frame, SearchSpaceFrame):
            raise ArgusValidationError(
                "search_space_frame must be a SearchSpaceFrame instance or None."
            )
        if self.coverage_ledger is not None and not isinstance(self.coverage_ledger, CoverageLedger):
            raise ArgusValidationError("coverage_ledger must be a CoverageLedger instance or None.")
        object.__setattr__(
            self,
            "scheduler_decisions",
            _normalize_scheduler_decisions(self.scheduler_decisions, "scheduler_decisions"),
        )
        object.__setattr__(
            self,
            "proposal_briefs",
            _normalize_proposal_briefs(self.proposal_briefs, "proposal_briefs"),
        )
        object.__setattr__(
            self,
            "triage_reports",
            _normalize_triage_reports(self.triage_reports, "triage_reports"),
        )
        object.__setattr__(
            self,
            "deep_dive_docs",
            _normalize_deep_dive_docs(self.deep_dive_docs, "deep_dive_docs"),
        )
        object.__setattr__(
            self,
            "adversarial_reviews",
            _normalize_adversarial_reviews(self.adversarial_reviews, "adversarial_reviews"),
        )
        object.__setattr__(
            self,
            "comparison_matrices",
            _normalize_comparison_matrices(self.comparison_matrices, "comparison_matrices"),
        )
        object.__setattr__(
            self,
            "hybrid_assessments",
            _normalize_hybrid_assessments(self.hybrid_assessments, "hybrid_assessments"),
        )
        if self.final_decision_doc is not None and not isinstance(self.final_decision_doc, FinalDecisionDoc):
            raise ArgusValidationError("final_decision_doc must be a FinalDecisionDoc instance or None.")

        frame = self.search_space_frame
        ledger = self.coverage_ledger
        if frame is not None and ledger is not None:
            if ledger.frame_id != frame.frame_id:
                raise ArgusValidationError("coverage_ledger.frame_id must match search_space_frame.frame_id.")
            axis_options = {axis.axis_id: set(axis.options) for axis in frame.axes}
            for cell in ledger.cells:
                unknown_axes = sorted(set(cell.axis_assignments) - set(axis_options))
                if unknown_axes:
                    raise ArgusValidationError(
                        f"SearchCell {cell.cell_id} references unknown axes: {', '.join(unknown_axes)}."
                    )
                for axis_id, choice in sorted(cell.axis_assignments.items()):
                    if choice not in axis_options[axis_id]:
                        raise ArgusValidationError(
                            f"SearchCell {cell.cell_id} uses invalid option {choice!r} for axis {axis_id!r}."
                        )

        proposal_ids = {brief.proposal_id for brief in self.proposal_briefs}
        cell_ids = set()
        if ledger is not None:
            cell_ids = {cell.cell_id for cell in ledger.cells}
            for cell in ledger.cells:
                unknown_incumbents = sorted(set(cell.incumbent_proposal_ids) - proposal_ids)
                if unknown_incumbents:
                    raise ArgusValidationError(
                        "coverage_ledger cells reference unknown proposal ids: "
                        f"{', '.join(unknown_incumbents)}."
                    )

        for brief in self.proposal_briefs:
            if cell_ids and brief.cell_id not in cell_ids:
                raise ArgusValidationError(
                    f"ProposalBrief {brief.proposal_id} references unknown cell_id {brief.cell_id!r}."
                )
        for decision in self.scheduler_decisions:
            unknown_cells = sorted(set(decision.target_cell_ids) - cell_ids)
            if cell_ids and unknown_cells:
                raise ArgusValidationError(
                    "SchedulerDecision references unknown cell ids: "
                    f"{', '.join(unknown_cells)}."
                )

        for report in self.triage_reports:
            if frame is not None and report.frame_id != frame.frame_id:
                raise ArgusValidationError("triage_reports frame_id must match search_space_frame.frame_id.")
            unknown_survivors = sorted(set(report.survivor_ids) - proposal_ids)
            if unknown_survivors:
                raise ArgusValidationError(
                    f"TriageReport {report.report_id} references unknown survivor_ids: {', '.join(unknown_survivors)}."
                )
            unknown_decisions = sorted(
                {decision.proposal_id for decision in report.decisions} - proposal_ids
            )
            if unknown_decisions:
                raise ArgusValidationError(
                    f"TriageReport {report.report_id} references unknown proposal ids: {', '.join(unknown_decisions)}."
                )
            if cell_ids:
                unknown_cells = sorted(set(report.unexplored_cell_ids) - cell_ids)
                if unknown_cells:
                    raise ArgusValidationError(
                        f"TriageReport {report.report_id} references unknown cell ids: {', '.join(unknown_cells)}."
                    )

        for doc in self.deep_dive_docs:
            if proposal_ids and doc.proposal_id not in proposal_ids:
                raise ArgusValidationError(
                    f"DeepDiveDoc {doc.doc_id} references unknown proposal_id {doc.proposal_id!r}."
                )
        for review in self.adversarial_reviews:
            if proposal_ids and review.proposal_id not in proposal_ids:
                raise ArgusValidationError(
                    "AdversarialReview "
                    f"{review.review_id} references unknown proposal_id {review.proposal_id!r}."
                )
        for matrix in self.comparison_matrices:
            if frame is not None and matrix.frame_id != frame.frame_id:
                raise ArgusValidationError(
                    "comparison_matrices frame_id must match search_space_frame.frame_id."
                )
            unknown_rows = sorted({row.proposal_id for row in matrix.rows} - proposal_ids)
            if unknown_rows:
                raise ArgusValidationError(
                    f"ComparisonMatrix {matrix.matrix_id} references unknown proposal ids: {', '.join(unknown_rows)}."
                )
        for assessment in self.hybrid_assessments:
            unknown_sources = sorted(set(assessment.source_proposal_ids) - proposal_ids)
            if unknown_sources:
                raise ArgusValidationError(
                    "HybridAssessment "
                    f"{assessment.assessment_id} references unknown proposal ids: {', '.join(unknown_sources)}."
                )
        for decision in self.scheduler_decisions:
            unknown_proposals = sorted(set(decision.target_proposal_ids) - proposal_ids)
            if proposal_ids and unknown_proposals:
                raise ArgusValidationError(
                    "SchedulerDecision references unknown proposal ids: "
                    f"{', '.join(unknown_proposals)}."
                )
        if self.final_decision_doc is not None:
            if frame is not None and self.final_decision_doc.frame_id != frame.frame_id:
                raise ArgusValidationError(
                    "final_decision_doc.frame_id must match search_space_frame.frame_id."
                )
            decision_refs = {
                self.final_decision_doc.selected_proposal_id,
                *(
                    ref
                    for ref in (
                        self.final_decision_doc.runner_up_proposal_id,
                        self.final_decision_doc.conservative_proposal_id,
                        self.final_decision_doc.high_upside_proposal_id,
                    )
                    if ref is not None
                ),
                *self.final_decision_doc.rejected_proposal_ids,
            }
            unknown_decision_refs = sorted(decision_refs - proposal_ids)
            if proposal_ids and unknown_decision_refs:
                raise ArgusValidationError(
                    "FinalDecisionDoc references unknown proposal ids: "
                    f"{', '.join(unknown_decision_refs)}."
                )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "scheduler_decisions": [decision.to_dict() for decision in self.scheduler_decisions],
            "proposal_briefs": [brief.to_dict() for brief in self.proposal_briefs],
            "triage_reports": [report.to_dict() for report in self.triage_reports],
            "deep_dive_docs": [doc.to_dict() for doc in self.deep_dive_docs],
            "adversarial_reviews": [review.to_dict() for review in self.adversarial_reviews],
            "comparison_matrices": [matrix.to_dict() for matrix in self.comparison_matrices],
            "hybrid_assessments": [assessment.to_dict() for assessment in self.hybrid_assessments],
        }
        if self.search_space_frame is not None:
            payload["search_space_frame"] = self.search_space_frame.to_dict()
        if self.coverage_ledger is not None:
            payload["coverage_ledger"] = self.coverage_ledger.to_dict()
        if self.final_decision_doc is not None:
            payload["final_decision_doc"] = self.final_decision_doc.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> "ResearchArtifactBundle":
        data = _validate_payload_keys(
            payload,
            field_name="ResearchArtifactBundle",
            required={
                "proposal_briefs",
                "triage_reports",
                "deep_dive_docs",
                "adversarial_reviews",
                "comparison_matrices",
                "hybrid_assessments",
            },
            optional={
                "search_space_frame",
                "coverage_ledger",
                "scheduler_decisions",
                "final_decision_doc",
            },
        )
        frame_payload = data.get("search_space_frame")
        ledger_payload = data.get("coverage_ledger")
        decision_payload = data.get("final_decision_doc")
        return cls(
            search_space_frame=None if frame_payload is None else SearchSpaceFrame.from_dict(frame_payload),
            coverage_ledger=None if ledger_payload is None else CoverageLedger.from_dict(ledger_payload),
            scheduler_decisions=[
                SchedulerDecision.from_dict(item)
                for item in _normalize_sequence(
                    data.get("scheduler_decisions", []),
                    "scheduler_decisions",
                )
            ],
            proposal_briefs=[
                ProposalBrief.from_dict(item)
                for item in _normalize_sequence(data["proposal_briefs"], "proposal_briefs")
            ],
            triage_reports=[
                TriageReport.from_dict(item)
                for item in _normalize_sequence(data["triage_reports"], "triage_reports")
            ],
            deep_dive_docs=[
                DeepDiveDoc.from_dict(item)
                for item in _normalize_sequence(data["deep_dive_docs"], "deep_dive_docs")
            ],
            adversarial_reviews=[
                AdversarialReview.from_dict(item)
                for item in _normalize_sequence(data["adversarial_reviews"], "adversarial_reviews")
            ],
            comparison_matrices=[
                ComparisonMatrix.from_dict(item)
                for item in _normalize_sequence(data["comparison_matrices"], "comparison_matrices")
            ],
            hybrid_assessments=[
                HybridAssessment.from_dict(item)
                for item in _normalize_sequence(data["hybrid_assessments"], "hybrid_assessments")
            ],
            final_decision_doc=None if decision_payload is None else FinalDecisionDoc.from_dict(decision_payload),
        )


def _normalize_string_mapping(value: object, field_name: str) -> dict[str, str]:
    mapping = _normalize_mapping(value, field_name)
    normalized: dict[str, str] = {}
    for key, item in sorted(mapping.items()):
        normalized[_normalize_non_empty_string(key, f"{field_name}.key")] = _normalize_non_empty_string(
            item,
            f"{field_name}.{key}",
        )
    return normalized


def _normalize_float_mapping(value: object, field_name: str) -> dict[str, float]:
    mapping = _normalize_mapping(value, field_name)
    normalized: dict[str, float] = {}
    for key, item in sorted(mapping.items()):
        normalized[_normalize_non_empty_string(key, f"{field_name}.key")] = _normalize_float(
            item,
            f"{field_name}.{key}",
        )
    return normalized


def _normalize_axes(value: object, field_name: str) -> list[SearchAxis]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[SearchAxis] = []
    seen: set[str] = set()
    for index, axis in enumerate(sequence):
        if not isinstance(axis, SearchAxis):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a SearchAxis instance, got {type(axis).__name__}."
            )
        if axis.axis_id in seen:
            raise ArgusValidationError(f"{field_name} contains duplicate axis_id values: {axis.axis_id}.")
        seen.add(axis.axis_id)
        normalized.append(axis)
    return normalized


def _normalize_cells(value: object, field_name: str) -> list[SearchCell]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[SearchCell] = []
    seen: set[str] = set()
    for index, cell in enumerate(sequence):
        if not isinstance(cell, SearchCell):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a SearchCell instance, got {type(cell).__name__}."
            )
        if cell.cell_id in seen:
            raise ArgusValidationError(f"{field_name} contains duplicate cell_id values: {cell.cell_id}.")
        seen.add(cell.cell_id)
        normalized.append(cell)
    return normalized


def _normalize_triage_decisions(value: object, field_name: str) -> list[ProposalTriageDecision]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[ProposalTriageDecision] = []
    seen: set[str] = set()
    for index, decision in enumerate(sequence):
        if not isinstance(decision, ProposalTriageDecision):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a ProposalTriageDecision instance, "
                f"got {type(decision).__name__}."
            )
        if decision.proposal_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate proposal_id values: {decision.proposal_id}."
            )
        seen.add(decision.proposal_id)
        normalized.append(decision)
    return normalized


def _normalize_matrix_rows(value: object, field_name: str) -> list[ComparisonMatrixRow]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[ComparisonMatrixRow] = []
    seen: set[str] = set()
    for index, row in enumerate(sequence):
        if not isinstance(row, ComparisonMatrixRow):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a ComparisonMatrixRow instance, got {type(row).__name__}."
            )
        if row.proposal_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate proposal_id values: {row.proposal_id}."
            )
        seen.add(row.proposal_id)
        normalized.append(row)
    return normalized


def _normalize_proposal_briefs(value: object, field_name: str) -> list[ProposalBrief]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[ProposalBrief] = []
    seen: set[str] = set()
    for index, brief in enumerate(sequence):
        if not isinstance(brief, ProposalBrief):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a ProposalBrief instance, got {type(brief).__name__}."
            )
        if brief.proposal_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate proposal_id values: {brief.proposal_id}."
            )
        seen.add(brief.proposal_id)
        normalized.append(brief)
    return normalized


def _normalize_scheduler_decisions(value: object, field_name: str) -> list[SchedulerDecision]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[SchedulerDecision] = []
    seen: set[str] = set()
    for index, decision in enumerate(sequence):
        if not isinstance(decision, SchedulerDecision):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a SchedulerDecision instance, got {type(decision).__name__}."
            )
        if decision.decision_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate decision_id values: {decision.decision_id}."
            )
        seen.add(decision.decision_id)
        normalized.append(decision)
    return normalized


def _normalize_triage_reports(value: object, field_name: str) -> list[TriageReport]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[TriageReport] = []
    seen: set[str] = set()
    for index, report in enumerate(sequence):
        if not isinstance(report, TriageReport):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a TriageReport instance, got {type(report).__name__}."
            )
        if report.report_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate report_id values: {report.report_id}."
            )
        seen.add(report.report_id)
        normalized.append(report)
    return normalized


def _normalize_deep_dive_docs(value: object, field_name: str) -> list[DeepDiveDoc]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[DeepDiveDoc] = []
    seen: set[str] = set()
    for index, doc in enumerate(sequence):
        if not isinstance(doc, DeepDiveDoc):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a DeepDiveDoc instance, got {type(doc).__name__}."
            )
        if doc.doc_id in seen:
            raise ArgusValidationError(f"{field_name} contains duplicate doc_id values: {doc.doc_id}.")
        seen.add(doc.doc_id)
        normalized.append(doc)
    return normalized


def _normalize_adversarial_reviews(value: object, field_name: str) -> list[AdversarialReview]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[AdversarialReview] = []
    seen: set[str] = set()
    for index, review in enumerate(sequence):
        if not isinstance(review, AdversarialReview):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be an AdversarialReview instance, "
                f"got {type(review).__name__}."
            )
        if review.review_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate review_id values: {review.review_id}."
            )
        seen.add(review.review_id)
        normalized.append(review)
    return normalized


def _normalize_comparison_matrices(value: object, field_name: str) -> list[ComparisonMatrix]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[ComparisonMatrix] = []
    seen: set[str] = set()
    for index, matrix in enumerate(sequence):
        if not isinstance(matrix, ComparisonMatrix):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a ComparisonMatrix instance, got {type(matrix).__name__}."
            )
        if matrix.matrix_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate matrix_id values: {matrix.matrix_id}."
            )
        seen.add(matrix.matrix_id)
        normalized.append(matrix)
    return normalized


def _normalize_hybrid_assessments(value: object, field_name: str) -> list[HybridAssessment]:
    sequence = _normalize_sequence(value, field_name)
    normalized: list[HybridAssessment] = []
    seen: set[str] = set()
    for index, assessment in enumerate(sequence):
        if not isinstance(assessment, HybridAssessment):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a HybridAssessment instance, got {type(assessment).__name__}."
            )
        if assessment.assessment_id in seen:
            raise ArgusValidationError(
                f"{field_name} contains duplicate assessment_id values: {assessment.assessment_id}."
            )
        seen.add(assessment.assessment_id)
        normalized.append(assessment)
    return normalized
