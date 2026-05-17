from __future__ import annotations

from dataclasses import dataclass

from argus.errors import ArgusValidationError
from argus.models import (
    AdversarialReview,
    ComparisonMatrix,
    DeepDiveDoc,
    FinalDecisionDoc,
    HybridAssessment,
    JSONValue,
    ProposalBrief,
    ResearchArtifactBundle,
    SearchSpaceFrame,
    TriageReport,
)
from argus.models.research import CoverageLedger
from argus.providers import StructuredOutputSchema


@dataclass(frozen=True, slots=True)
class SearchSpacePlan:
    search_space_frame: SearchSpaceFrame
    coverage_ledger: CoverageLedger

    def __post_init__(self) -> None:
        if not isinstance(self.search_space_frame, SearchSpaceFrame):
            raise ArgusValidationError(
                "search_space_frame must be a SearchSpaceFrame instance, "
                f"got {type(self.search_space_frame).__name__}."
            )
        if not isinstance(self.coverage_ledger, CoverageLedger):
            raise ArgusValidationError(
                "coverage_ledger must be a CoverageLedger instance, "
                f"got {type(self.coverage_ledger).__name__}."
            )
        if self.coverage_ledger.frame_id != self.search_space_frame.frame_id:
            raise ArgusValidationError(
                "coverage_ledger.frame_id must match search_space_frame.frame_id."
            )
        ResearchArtifactBundle(
            search_space_frame=self.search_space_frame,
            coverage_ledger=self.coverage_ledger,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "search_space_frame": self.search_space_frame.to_dict(),
            "coverage_ledger": self.coverage_ledger.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "SearchSpacePlan":
        if not isinstance(payload, dict):
            raise ArgusValidationError(
                f"SearchSpacePlan must be an object, got {type(payload).__name__}."
            )
        expected = {"search_space_frame", "coverage_ledger"}
        actual = set(payload)
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        if extra or missing:
            details: list[str] = []
            if missing:
                details.append("missing keys: " + ", ".join(missing))
            if extra:
                details.append("unexpected keys: " + ", ".join(extra))
            raise ArgusValidationError("SearchSpacePlan payload invalid: " + "; ".join(details))
        return cls(
            search_space_frame=SearchSpaceFrame.from_dict(payload["search_space_frame"]),
            coverage_ledger=CoverageLedger.from_dict(payload["coverage_ledger"]),
        )


@dataclass(frozen=True, slots=True)
class ProposalSeedBatch:
    proposals: list[ProposalBrief]
    batch_summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.batch_summary, str) or not self.batch_summary.strip():
            raise ArgusValidationError("batch_summary must be a non-empty string.")
        if not isinstance(self.proposals, list) or not self.proposals:
            raise ArgusValidationError("proposals must be a non-empty list of ProposalBrief objects.")
        proposal_ids: set[str] = set()
        for index, proposal in enumerate(self.proposals):
            if not isinstance(proposal, ProposalBrief):
                raise ArgusValidationError(
                    f"proposals[{index}] must be a ProposalBrief instance, got {type(proposal).__name__}."
                )
            if proposal.proposal_id in proposal_ids:
                raise ArgusValidationError(
                    f"proposals contains duplicate proposal_id values: {proposal.proposal_id}."
                )
            proposal_ids.add(proposal.proposal_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "batch_summary": self.batch_summary.strip(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ProposalSeedBatch":
        if not isinstance(payload, dict):
            raise ArgusValidationError(
                f"ProposalSeedBatch must be an object, got {type(payload).__name__}."
            )
        expected = {"proposals", "batch_summary"}
        actual = set(payload)
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        if extra or missing:
            details: list[str] = []
            if missing:
                details.append("missing keys: " + ", ".join(missing))
            if extra:
                details.append("unexpected keys: " + ", ".join(extra))
            raise ArgusValidationError("ProposalSeedBatch payload invalid: " + "; ".join(details))
        proposals_payload = payload["proposals"]
        if not isinstance(proposals_payload, list):
            raise ArgusValidationError("proposals must be a list.")
        return cls(
            proposals=[ProposalBrief.from_dict(item) for item in proposals_payload],
            batch_summary=payload["batch_summary"],
        )


@dataclass(frozen=True, slots=True)
class FinalDecisionPackage:
    comparison_matrix: ComparisonMatrix
    final_decision_doc: FinalDecisionDoc
    decision_summary_markdown: str
    decision_report_markdown: str

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_matrix, ComparisonMatrix):
            raise ArgusValidationError(
                "comparison_matrix must be a ComparisonMatrix instance, "
                f"got {type(self.comparison_matrix).__name__}."
            )
        if not isinstance(self.final_decision_doc, FinalDecisionDoc):
            raise ArgusValidationError(
                "final_decision_doc must be a FinalDecisionDoc instance, "
                f"got {type(self.final_decision_doc).__name__}."
            )
        if not isinstance(self.decision_summary_markdown, str) or not self.decision_summary_markdown.strip():
            raise ArgusValidationError("decision_summary_markdown must be a non-empty string.")
        if not isinstance(self.decision_report_markdown, str) or not self.decision_report_markdown.strip():
            raise ArgusValidationError("decision_report_markdown must be a non-empty string.")
        if self.comparison_matrix.frame_id != self.final_decision_doc.frame_id:
            raise ArgusValidationError(
                "comparison_matrix.frame_id must match final_decision_doc.frame_id."
            )
        proposal_ids = {row.proposal_id for row in self.comparison_matrix.rows}
        referenced_ids = {
            self.final_decision_doc.selected_proposal_id,
            *(
                proposal_id
                for proposal_id in (
                    self.final_decision_doc.runner_up_proposal_id,
                    self.final_decision_doc.conservative_proposal_id,
                    self.final_decision_doc.high_upside_proposal_id,
                )
                if proposal_id is not None
            ),
            *self.final_decision_doc.rejected_proposal_ids,
        }
        unknown_ids = sorted(referenced_ids - proposal_ids)
        if unknown_ids:
            raise ArgusValidationError(
                "final_decision_doc references proposal ids missing from comparison_matrix rows: "
                + ", ".join(unknown_ids)
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_matrix": self.comparison_matrix.to_dict(),
            "final_decision_doc": self.final_decision_doc.to_dict(),
            "decision_summary_markdown": self.decision_summary_markdown.strip(),
            "decision_report_markdown": self.decision_report_markdown.strip(),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "FinalDecisionPackage":
        if not isinstance(payload, dict):
            raise ArgusValidationError(
                f"FinalDecisionPackage must be an object, got {type(payload).__name__}."
            )
        expected = {
            "comparison_matrix",
            "final_decision_doc",
            "decision_summary_markdown",
            "decision_report_markdown",
        }
        actual = set(payload)
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        if extra or missing:
            details: list[str] = []
            if missing:
                details.append("missing keys: " + ", ".join(missing))
            if extra:
                details.append("unexpected keys: " + ", ".join(extra))
            raise ArgusValidationError("FinalDecisionPackage payload invalid: " + "; ".join(details))
        return cls(
            comparison_matrix=ComparisonMatrix.from_dict(payload["comparison_matrix"]),
            final_decision_doc=FinalDecisionDoc.from_dict(payload["final_decision_doc"]),
            decision_summary_markdown=payload["decision_summary_markdown"],
            decision_report_markdown=payload["decision_report_markdown"],
        )


def search_space_plan_schema() -> StructuredOutputSchema[SearchSpacePlan]:
    return StructuredOutputSchema(
        name="search_space_plan",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["search_space_frame", "coverage_ledger"],
            "properties": {
                "search_space_frame": _search_space_frame_schema(),
                "coverage_ledger": _coverage_ledger_schema(),
            },
        },
        validator=SearchSpacePlan.from_dict,
    )


def proposal_seed_batch_schema() -> StructuredOutputSchema[ProposalSeedBatch]:
    return StructuredOutputSchema(
        name="proposal_seed_batch",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["proposals", "batch_summary"],
            "properties": {
                "proposals": {
                    "type": "array",
                    "minItems": 1,
                    "items": _proposal_brief_schema(),
                },
                "batch_summary": {"type": "string", "minLength": 1},
            },
        },
        validator=ProposalSeedBatch.from_dict,
    )


def triage_report_schema() -> StructuredOutputSchema[TriageReport]:
    return StructuredOutputSchema(
        name="triage_report",
        json_schema=_triage_report_schema(),
        validator=TriageReport.from_dict,
    )


def deep_dive_doc_schema() -> StructuredOutputSchema[DeepDiveDoc]:
    return StructuredOutputSchema(
        name="deep_dive_doc",
        json_schema=_deep_dive_doc_schema(),
        validator=DeepDiveDoc.from_dict,
    )


def adversarial_review_schema() -> StructuredOutputSchema[AdversarialReview]:
    return StructuredOutputSchema(
        name="adversarial_review",
        json_schema=_adversarial_review_schema(),
        validator=AdversarialReview.from_dict,
    )


def hybrid_assessment_schema() -> StructuredOutputSchema[HybridAssessment]:
    return StructuredOutputSchema(
        name="hybrid_assessment",
        json_schema=_hybrid_assessment_schema(),
        validator=HybridAssessment.from_dict,
    )


def final_decision_package_schema() -> StructuredOutputSchema[FinalDecisionPackage]:
    return StructuredOutputSchema(
        name="final_decision_package",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "comparison_matrix",
                "final_decision_doc",
                "decision_summary_markdown",
                "decision_report_markdown",
            ],
            "properties": {
                "comparison_matrix": _comparison_matrix_schema(),
                "final_decision_doc": _final_decision_doc_schema(),
                "decision_summary_markdown": {"type": "string", "minLength": 1},
                "decision_report_markdown": {"type": "string", "minLength": 1},
            },
        },
        validator=FinalDecisionPackage.from_dict,
    )


def _search_space_frame_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "frame_id",
            "problem_statement",
            "target_decision",
            "hard_gates",
            "soft_criteria",
            "baseline_options",
            "axes",
            "coverage_plan",
            "notes",
        ],
        "properties": {
            "frame_id": {"type": "string", "minLength": 1},
            "problem_statement": {"type": "string", "minLength": 1},
            "target_decision": {"type": "string", "minLength": 1},
            "hard_gates": _string_array_schema(),
            "soft_criteria": _string_array_schema(),
            "baseline_options": _string_array_schema(),
            "axes": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["axis_id", "label", "description", "options", "rationale"],
                    "properties": {
                        "axis_id": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "options": {
                            "type": "array",
                            "minItems": 2,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "rationale": {"type": ["string", "null"], "minLength": 1},
                    },
                },
            },
            "coverage_plan": _string_array_schema(),
            "notes": _string_array_schema(),
        },
    }


def _coverage_ledger_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "ledger_id",
            "frame_id",
            "cells",
            "coverage_summary",
            "next_questions",
            "updated_at",
        ],
        "properties": {
            "ledger_id": {"type": "string", "minLength": 1},
            "frame_id": {"type": "string", "minLength": 1},
            "cells": {
                "type": "array",
                "minItems": 1,
                "items": _search_cell_schema(),
            },
            "coverage_summary": {"type": "string", "minLength": 1},
            "next_questions": _string_array_schema(),
            "updated_at": {"type": "string", "minLength": 1},
        },
    }


def _axis_assignment_entry_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["axis_id", "choice"],
        "properties": {
            "axis_id": {"type": "string", "minLength": 1},
            "choice": {"type": "string", "minLength": 1},
        },
    }


def _criterion_score_entry_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["criterion_id", "score"],
        "properties": {
            "criterion_id": {"type": "string", "minLength": 1},
            "score": {"type": "number"},
        },
    }


def _search_cell_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
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
        ],
        "properties": {
            "cell_id": {"type": "string", "minLength": 1},
            "label": {"type": "string", "minLength": 1},
            "axis_assignments": {
                "type": "array",
                "minItems": 1,
                "items": _axis_assignment_entry_schema(),
            },
            "hypothesis": {"type": "string", "minLength": 1},
            "coverage_status": {
                "type": "string",
                "enum": [
                    "unexplored",
                    "seeded",
                    "triaged",
                    "deepened",
                    "redteamed",
                    "closed",
                    "dominated",
                ],
            },
            "uncertainty": {"type": "number"},
            "hard_gate_risk": {"type": "number"},
            "evidence_strength": {"type": "number"},
            "incumbent_proposal_ids": _string_array_schema(),
            "notes": _string_array_schema(),
        },
    }


def _proposal_brief_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "proposal_id",
            "cell_id",
            "title",
            "summary",
            "candidate",
            "seed_rationale",
            "open_questions",
            "evidence",
            "parent_node_ids",
        ],
        "properties": {
            "proposal_id": {"type": "string", "minLength": 1},
            "cell_id": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "summary": {"type": "string", "minLength": 1},
            "candidate": _candidate_schema(),
            "seed_rationale": {"type": "string", "minLength": 1},
            "open_questions": _string_array_schema(),
            "evidence": _string_array_schema(),
            "parent_node_ids": _string_array_schema(),
        },
    }


def _triage_report_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "report_id",
            "frame_id",
            "decisions",
            "survivor_ids",
            "unexplored_cell_ids",
            "summary",
            "next_actions",
        ],
        "properties": {
            "report_id": {"type": "string", "minLength": 1},
            "frame_id": {"type": "string", "minLength": 1},
            "decisions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "proposal_id",
                        "disposition",
                        "rationale",
                        "merged_into_proposal_id",
                        "follow_up",
                    ],
                    "properties": {
                        "proposal_id": {"type": "string", "minLength": 1},
                        "disposition": {
                            "type": "string",
                            "enum": ["survive", "eliminate", "collapse"],
                        },
                        "rationale": {"type": "string", "minLength": 1},
                        "merged_into_proposal_id": {"type": ["string", "null"], "minLength": 1},
                        "follow_up": {"type": ["string", "null"], "minLength": 1},
                    },
                },
            },
            "survivor_ids": _string_array_schema(),
            "unexplored_cell_ids": _string_array_schema(),
            "summary": {"type": "string", "minLength": 1},
            "next_actions": _string_array_schema(),
        },
    }


def _deep_dive_doc_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "doc_id",
            "proposal_id",
            "title",
            "executive_summary",
            "detailed_mechanism",
            "implementation_plan",
            "key_unknowns",
            "supporting_evidence",
            "assumptions",
            "technical_dossier_markdown",
        ],
        "properties": {
            "doc_id": {"type": "string", "minLength": 1},
            "proposal_id": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "executive_summary": {"type": "string", "minLength": 1},
            "detailed_mechanism": {"type": "string", "minLength": 1},
            "implementation_plan": _string_array_schema(),
            "key_unknowns": _string_array_schema(),
            "supporting_evidence": _string_array_schema(),
            "assumptions": _string_array_schema(),
            "technical_dossier_markdown": {"type": "string", "minLength": 800},
        },
    }


def _adversarial_review_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
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
        ],
        "properties": {
            "review_id": {"type": "string", "minLength": 1},
            "proposal_id": {"type": "string", "minLength": 1},
            "thesis_under_test": {"type": "string", "minLength": 1},
            "hidden_dependencies": _string_array_schema(),
            "failure_modes": _string_array_schema(),
            "mitigations": _string_array_schema(),
            "summary": {"type": "string", "minLength": 1},
            "verdict": {"type": "string", "minLength": 1},
            "confidence": {"type": "number"},
            "evidence": _string_array_schema(),
        },
    }


def _comparison_matrix_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["matrix_id", "frame_id", "criteria", "rows", "summary"],
        "properties": {
            "matrix_id": {"type": "string", "minLength": 1},
            "frame_id": {"type": "string", "minLength": 1},
            "criteria": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "rows": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "proposal_id",
                        "criterion_scores",
                        "advantages",
                        "liabilities",
                        "takeaway",
                    ],
                    "properties": {
                        "proposal_id": {"type": "string", "minLength": 1},
                        "criterion_scores": {"type": "array", "minItems": 1, "items": _criterion_score_entry_schema()},
                        "advantages": _string_array_schema(),
                        "liabilities": _string_array_schema(),
                        "takeaway": {"type": "string", "minLength": 1},
                    },
                },
            },
            "summary": {"type": "string", "minLength": 1},
        },
    }


def _hybrid_assessment_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
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
        ],
        "properties": {
            "assessment_id": {"type": "string", "minLength": 1},
            "source_proposal_ids": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string", "minLength": 1},
            },
            "hybrid_name": {"type": "string", "minLength": 1},
            "seam_hypothesis": {"type": "string", "minLength": 1},
            "repaired_failure_mode": {"type": "string", "minLength": 1},
            "complementary_strengths": _string_array_schema(),
            "complexity_tax": {"type": "string", "minLength": 1},
            "expected_upside": {"type": "string", "minLength": 1},
            "open_questions": _string_array_schema(),
            "verdict": {"type": "string", "enum": ["pursue", "hold", "reject"]},
            "summary": {"type": "string", "minLength": 1},
        },
    }


def _final_decision_doc_schema() -> dict[str, JSONValue]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "decision_id",
            "frame_id",
            "selected_proposal_id",
            "runner_up_proposal_id",
            "conservative_proposal_id",
            "high_upside_proposal_id",
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
        ],
        "properties": {
            "decision_id": {"type": "string", "minLength": 1},
            "frame_id": {"type": "string", "minLength": 1},
            "selected_proposal_id": {"type": "string", "minLength": 1},
            "runner_up_proposal_id": {"type": ["string", "null"], "minLength": 1},
            "conservative_proposal_id": {"type": ["string", "null"], "minLength": 1},
            "high_upside_proposal_id": {"type": ["string", "null"], "minLength": 1},
            "summary": {"type": "string", "minLength": 1},
            "decision_rule": {"type": "string", "minLength": 1},
            "assumptions": _string_array_schema(),
            "top_risks": _string_array_schema(),
            "mitigations": _string_array_schema(),
            "first_spike": _string_array_schema(),
            "kill_criteria": _string_array_schema(),
            "next_experiments": _string_array_schema(),
            "reversal_conditions": _string_array_schema(),
            "rejected_proposal_ids": _string_array_schema(),
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
            "implementation_shape": {"type": ["string", "null"], "minLength": 1},
            "evidence": _string_array_schema(),
        },
    }


def _string_array_schema() -> dict[str, JSONValue]:
    return {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
    }
