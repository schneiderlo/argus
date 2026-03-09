from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import re

from argus.errors import ArgusValidationError
from argus.models import ProblemSpec

_CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class BenchmarkFamily(StrEnum):
    PRODUCT_STRATEGY = "product_strategy"
    GROWTH = "growth"
    UX = "ux"
    TECHNICAL_ARCHITECTURE = "technical_architecture"
    MONETIZATION = "monetization"


class BenchmarkStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class BenchmarkComparisonStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BenchmarkRuntimeMode(StrEnum):
    ADAPTIVE = "adaptive"
    STAGED = "staged"
    RESEARCH = "research"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    title: str
    family: BenchmarkFamily
    problem_spec: ProblemSpec
    budget: int = 12
    evaluation_notes: list[str] = field(default_factory=list)
    expected_qualities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _normalize_case_id(self.case_id, "case_id"))
        object.__setattr__(self, "title", _normalize_non_empty_string(self.title, "title"))
        object.__setattr__(self, "family", _normalize_enum(self.family, BenchmarkFamily, "family"))
        if not isinstance(self.problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(self.problem_spec).__name__}."
            )
        object.__setattr__(self, "budget", _normalize_positive_int(self.budget, "budget"))
        object.__setattr__(
            self,
            "evaluation_notes",
            _normalize_string_list(self.evaluation_notes, "evaluation_notes"),
        )
        object.__setattr__(
            self,
            "expected_qualities",
            _normalize_string_list(self.expected_qualities, "expected_qualities"),
        )
        object.__setattr__(self, "tags", _normalize_unique_string_list(self.tags, "tags"))
        if not self.evaluation_notes:
            raise ArgusValidationError("evaluation_notes must include at least one item.")
        if not self.expected_qualities:
            raise ArgusValidationError("expected_qualities must include at least one item.")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "family": self.family.value,
            "problem_spec": self.problem_spec.to_dict(),
            "budget": self.budget,
            "evaluation_notes": list(self.evaluation_notes),
            "expected_qualities": list(self.expected_qualities),
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkCase":
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkCase",
            required={
                "case_id",
                "title",
                "family",
                "problem_spec",
                "budget",
                "evaluation_notes",
                "expected_qualities",
                "tags",
            },
        )
        return cls(
            case_id=data["case_id"],
            title=data["title"],
            family=data["family"],
            problem_spec=ProblemSpec.from_dict(data["problem_spec"]),
            budget=data["budget"],
            evaluation_notes=data["evaluation_notes"],
            expected_qualities=data["expected_qualities"],
            tags=data["tags"],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkModeJudgment:
    runtime_mode: BenchmarkRuntimeMode
    decision_quality: float
    actionability: float
    tradeoff_clarity: float
    risk_quality: float
    experiment_quality: float
    overall_score: float
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_mode",
            _normalize_enum(self.runtime_mode, BenchmarkRuntimeMode, "runtime_mode"),
        )
        for field_name in (
            "decision_quality",
            "actionability",
            "tradeoff_clarity",
            "risk_quality",
            "experiment_quality",
            "overall_score",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_probability(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "strengths", _normalize_string_list(self.strengths, "strengths"))
        object.__setattr__(self, "weaknesses", _normalize_string_list(self.weaknesses, "weaknesses"))
        object.__setattr__(self, "evidence", _normalize_string_list(self.evidence, "evidence"))

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_mode": self.runtime_mode.value,
            "decision_quality": self.decision_quality,
            "actionability": self.actionability,
            "tradeoff_clarity": self.tradeoff_clarity,
            "risk_quality": self.risk_quality,
            "experiment_quality": self.experiment_quality,
            "overall_score": self.overall_score,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkModeJudgment":
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkModeJudgment",
            required={
                "runtime_mode",
                "decision_quality",
                "actionability",
                "tradeoff_clarity",
                "risk_quality",
                "experiment_quality",
                "overall_score",
                "strengths",
                "weaknesses",
                "evidence",
            },
        )
        return cls(
            runtime_mode=data["runtime_mode"],
            decision_quality=data["decision_quality"],
            actionability=data["actionability"],
            tradeoff_clarity=data["tradeoff_clarity"],
            risk_quality=data["risk_quality"],
            experiment_quality=data["experiment_quality"],
            overall_score=data["overall_score"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            evidence=data["evidence"],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkComparisonAssessment:
    winner_runtime_mode: BenchmarkRuntimeMode
    runner_up_runtime_mode: BenchmarkRuntimeMode
    summary: str
    confidence: float
    decisive_reasons: list[str] = field(default_factory=list)
    watchouts: list[str] = field(default_factory=list)
    mode_judgments: list[BenchmarkModeJudgment] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "winner_runtime_mode",
            _normalize_enum(
                self.winner_runtime_mode,
                BenchmarkRuntimeMode,
                "winner_runtime_mode",
            ),
        )
        object.__setattr__(
            self,
            "runner_up_runtime_mode",
            _normalize_enum(
                self.runner_up_runtime_mode,
                BenchmarkRuntimeMode,
                "runner_up_runtime_mode",
            ),
        )
        if self.runner_up_runtime_mode is self.winner_runtime_mode:
            raise ArgusValidationError(
                "runner_up_runtime_mode must differ from winner_runtime_mode."
            )
        object.__setattr__(self, "summary", _normalize_non_empty_string(self.summary, "summary"))
        object.__setattr__(self, "confidence", _normalize_probability(self.confidence, "confidence"))
        object.__setattr__(
            self,
            "decisive_reasons",
            _normalize_string_list(self.decisive_reasons, "decisive_reasons"),
        )
        object.__setattr__(self, "watchouts", _normalize_string_list(self.watchouts, "watchouts"))
        object.__setattr__(
            self,
            "mode_judgments",
            _normalize_mode_judgments(self.mode_judgments, "mode_judgments"),
        )
        if len(self.mode_judgments) < 2:
            raise ArgusValidationError("mode_judgments must include at least two runtime modes.")
        judgment_modes = [judgment.runtime_mode for judgment in self.mode_judgments]
        if self.winner_runtime_mode not in judgment_modes:
            raise ArgusValidationError(
                "winner_runtime_mode must appear in mode_judgments."
            )
        if self.runner_up_runtime_mode not in judgment_modes:
            raise ArgusValidationError(
                "runner_up_runtime_mode must appear in mode_judgments."
            )
        if not self.decisive_reasons:
            raise ArgusValidationError(
                "decisive_reasons must include at least one item."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "winner_runtime_mode": self.winner_runtime_mode.value,
            "runner_up_runtime_mode": self.runner_up_runtime_mode.value,
            "summary": self.summary,
            "confidence": self.confidence,
            "decisive_reasons": list(self.decisive_reasons),
            "watchouts": list(self.watchouts),
            "mode_judgments": [judgment.to_dict() for judgment in self.mode_judgments],
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkComparisonAssessment":
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkComparisonAssessment",
            required={
                "winner_runtime_mode",
                "runner_up_runtime_mode",
                "summary",
                "confidence",
                "decisive_reasons",
                "watchouts",
                "mode_judgments",
            },
        )
        return cls(
            winner_runtime_mode=data["winner_runtime_mode"],
            runner_up_runtime_mode=data["runner_up_runtime_mode"],
            summary=data["summary"],
            confidence=data["confidence"],
            decisive_reasons=data["decisive_reasons"],
            watchouts=data["watchouts"],
            mode_judgments=[
                BenchmarkModeJudgment.from_dict(item)
                for item in _normalize_sequence(data["mode_judgments"], "mode_judgments")
            ],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkCaseComparison:
    case_id: str
    family: BenchmarkFamily
    runtime_modes: list[BenchmarkRuntimeMode]
    status: BenchmarkComparisonStatus
    assessment: BenchmarkComparisonAssessment | None = None
    comparison_path: str | None = None
    markdown_path: str | None = None
    error: str | None = None
    failure_type: str | None = None
    skipped_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _normalize_case_id(self.case_id, "case_id"))
        object.__setattr__(self, "family", _normalize_enum(self.family, BenchmarkFamily, "family"))
        object.__setattr__(
            self,
            "runtime_modes",
            _normalize_runtime_modes(self.runtime_modes, "runtime_modes"),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_enum(self.status, BenchmarkComparisonStatus, "status"),
        )
        object.__setattr__(
            self,
            "assessment",
            _normalize_optional_benchmark_comparison_assessment(
                self.assessment,
                "assessment",
            ),
        )
        object.__setattr__(
            self,
            "comparison_path",
            _normalize_optional_string(self.comparison_path, "comparison_path"),
        )
        object.__setattr__(
            self,
            "markdown_path",
            _normalize_optional_string(self.markdown_path, "markdown_path"),
        )
        object.__setattr__(self, "error", _normalize_optional_string(self.error, "error"))
        object.__setattr__(
            self,
            "failure_type",
            _normalize_optional_string(self.failure_type, "failure_type"),
        )
        object.__setattr__(
            self,
            "skipped_reason",
            _normalize_optional_string(self.skipped_reason, "skipped_reason"),
        )

        if self.status is BenchmarkComparisonStatus.COMPLETED:
            if self.assessment is None:
                raise ArgusValidationError(
                    "Completed benchmark case comparisons require assessment."
                )
            if len(self.runtime_modes) < 2:
                raise ArgusValidationError(
                    "Completed benchmark case comparisons require at least two runtime modes."
                )
            judgment_modes = [judgment.runtime_mode for judgment in self.assessment.mode_judgments]
            if judgment_modes != self.runtime_modes:
                raise ArgusValidationError(
                    "assessment.mode_judgments must align exactly with runtime_modes order."
                )
            if self.error is not None or self.failure_type is not None or self.skipped_reason is not None:
                raise ArgusValidationError(
                    "Completed benchmark case comparisons cannot include failure or skip details."
                )
        elif self.status is BenchmarkComparisonStatus.FAILED:
            if self.error is None or self.failure_type is None:
                raise ArgusValidationError(
                    "Failed benchmark case comparisons require both error and failure_type."
                )
            if self.assessment is not None or self.skipped_reason is not None:
                raise ArgusValidationError(
                    "Failed benchmark case comparisons cannot include assessment or skipped_reason."
                )
        else:
            if self.skipped_reason is None:
                raise ArgusValidationError(
                    "Skipped benchmark case comparisons require skipped_reason."
                )
            if self.assessment is not None or self.error is not None or self.failure_type is not None:
                raise ArgusValidationError(
                    "Skipped benchmark case comparisons cannot include assessment or failure details."
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "family": self.family.value,
            "runtime_modes": [mode.value for mode in self.runtime_modes],
            "status": self.status.value,
            "assessment": None if self.assessment is None else self.assessment.to_dict(),
            "comparison_path": self.comparison_path,
            "markdown_path": self.markdown_path,
            "error": self.error,
            "failure_type": self.failure_type,
            "skipped_reason": self.skipped_reason,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkCaseComparison":
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkCaseComparison",
            required={
                "case_id",
                "family",
                "runtime_modes",
                "status",
                "assessment",
                "comparison_path",
                "markdown_path",
                "error",
                "failure_type",
                "skipped_reason",
            },
        )
        assessment_payload = data["assessment"]
        return cls(
            case_id=data["case_id"],
            family=data["family"],
            runtime_modes=data["runtime_modes"],
            status=data["status"],
            assessment=(
                None
                if assessment_payload is None
                else BenchmarkComparisonAssessment.from_dict(assessment_payload)
            ),
            comparison_path=data["comparison_path"],
            markdown_path=data["markdown_path"],
            error=data["error"],
            failure_type=data["failure_type"],
            skipped_reason=data["skipped_reason"],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    case_id: str
    family: BenchmarkFamily
    runtime_mode: BenchmarkRuntimeMode
    status: BenchmarkStatus
    run_id: str | None = None
    run_path: str | None = None
    output_digest: str | None = None
    previous_output_digest: str | None = None
    changed_from_previous: bool | None = None
    best_bet_node_id: str | None = None
    best_bet_thesis: str | None = None
    conservative_node_id: str | None = None
    conservative_thesis: str | None = None
    high_upside_node_id: str | None = None
    high_upside_thesis: str | None = None
    summary_path: str | None = None
    final_recommendation_path: str | None = None
    error: str | None = None
    failure_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _normalize_case_id(self.case_id, "case_id"))
        object.__setattr__(self, "family", _normalize_enum(self.family, BenchmarkFamily, "family"))
        object.__setattr__(
            self,
            "runtime_mode",
            _normalize_enum(self.runtime_mode, BenchmarkRuntimeMode, "runtime_mode"),
        )
        object.__setattr__(self, "status", _normalize_enum(self.status, BenchmarkStatus, "status"))
        object.__setattr__(self, "run_id", _normalize_optional_string(self.run_id, "run_id"))
        object.__setattr__(self, "run_path", _normalize_optional_string(self.run_path, "run_path"))
        object.__setattr__(
            self,
            "output_digest",
            _normalize_optional_string(self.output_digest, "output_digest"),
        )
        object.__setattr__(
            self,
            "previous_output_digest",
            _normalize_optional_string(self.previous_output_digest, "previous_output_digest"),
        )
        object.__setattr__(
            self,
            "changed_from_previous",
            _normalize_optional_bool(self.changed_from_previous, "changed_from_previous"),
        )
        object.__setattr__(
            self,
            "best_bet_node_id",
            _normalize_optional_string(self.best_bet_node_id, "best_bet_node_id"),
        )
        object.__setattr__(
            self,
            "best_bet_thesis",
            _normalize_optional_string(self.best_bet_thesis, "best_bet_thesis"),
        )
        object.__setattr__(
            self,
            "conservative_node_id",
            _normalize_optional_string(self.conservative_node_id, "conservative_node_id"),
        )
        object.__setattr__(
            self,
            "conservative_thesis",
            _normalize_optional_string(self.conservative_thesis, "conservative_thesis"),
        )
        object.__setattr__(
            self,
            "high_upside_node_id",
            _normalize_optional_string(self.high_upside_node_id, "high_upside_node_id"),
        )
        object.__setattr__(
            self,
            "high_upside_thesis",
            _normalize_optional_string(self.high_upside_thesis, "high_upside_thesis"),
        )
        object.__setattr__(
            self,
            "summary_path",
            _normalize_optional_string(self.summary_path, "summary_path"),
        )
        object.__setattr__(
            self,
            "final_recommendation_path",
            _normalize_optional_string(
                self.final_recommendation_path,
                "final_recommendation_path",
            ),
        )
        object.__setattr__(self, "error", _normalize_optional_string(self.error, "error"))
        object.__setattr__(
            self,
            "failure_type",
            _normalize_optional_string(self.failure_type, "failure_type"),
        )
        if self.changed_from_previous is not None and self.previous_output_digest is None:
            raise ArgusValidationError(
                "previous_output_digest must be set when changed_from_previous is provided."
            )
        if self.status is BenchmarkStatus.COMPLETED:
            required_completed_fields = {
                "run_id": self.run_id,
                "run_path": self.run_path,
                "output_digest": self.output_digest,
                "best_bet_node_id": self.best_bet_node_id,
                "best_bet_thesis": self.best_bet_thesis,
                "summary_path": self.summary_path,
                "final_recommendation_path": self.final_recommendation_path,
            }
            missing = [name for name, value in required_completed_fields.items() if value is None]
            if missing:
                raise ArgusValidationError(
                    "Completed benchmark case results require: " + ", ".join(sorted(missing))
                )
            if self.error is not None or self.failure_type is not None:
                raise ArgusValidationError(
                    "Completed benchmark case results cannot include failure details."
                )
        if self.status is BenchmarkStatus.FAILED:
            if self.error is None or self.failure_type is None:
                raise ArgusValidationError(
                    "Failed benchmark case results require both error and failure_type."
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "family": self.family.value,
            "runtime_mode": self.runtime_mode.value,
            "status": self.status.value,
            "run_id": self.run_id,
            "run_path": self.run_path,
            "output_digest": self.output_digest,
            "previous_output_digest": self.previous_output_digest,
            "changed_from_previous": self.changed_from_previous,
            "best_bet_node_id": self.best_bet_node_id,
            "best_bet_thesis": self.best_bet_thesis,
            "conservative_node_id": self.conservative_node_id,
            "conservative_thesis": self.conservative_thesis,
            "high_upside_node_id": self.high_upside_node_id,
            "high_upside_thesis": self.high_upside_thesis,
            "summary_path": self.summary_path,
            "final_recommendation_path": self.final_recommendation_path,
            "error": self.error,
            "failure_type": self.failure_type,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkCaseResult":
        if not isinstance(payload, dict):
            raise ArgusValidationError(
                f"BenchmarkCaseResult must be an object, got {type(payload).__name__}."
            )
        raw_payload = dict(payload)
        raw_payload.setdefault("runtime_mode", BenchmarkRuntimeMode.ADAPTIVE.value)
        data = _validate_payload_keys(
            raw_payload,
            field_name="BenchmarkCaseResult",
            required={
                "case_id",
                "family",
                "runtime_mode",
                "status",
                "run_id",
                "run_path",
                "output_digest",
                "previous_output_digest",
                "changed_from_previous",
                "best_bet_node_id",
                "best_bet_thesis",
                "conservative_node_id",
                "conservative_thesis",
                "high_upside_node_id",
                "high_upside_thesis",
                "summary_path",
                "final_recommendation_path",
                "error",
                "failure_type",
            },
        )
        return cls(
            case_id=data["case_id"],
            family=data["family"],
            runtime_mode=data["runtime_mode"],
            status=data["status"],
            run_id=data["run_id"],
            run_path=data["run_path"],
            output_digest=data["output_digest"],
            previous_output_digest=data["previous_output_digest"],
            changed_from_previous=data["changed_from_previous"],
            best_bet_node_id=data["best_bet_node_id"],
            best_bet_thesis=data["best_bet_thesis"],
            conservative_node_id=data["conservative_node_id"],
            conservative_thesis=data["conservative_thesis"],
            high_upside_node_id=data["high_upside_node_id"],
            high_upside_thesis=data["high_upside_thesis"],
            summary_path=data["summary_path"],
            final_recommendation_path=data["final_recommendation_path"],
            error=data["error"],
            failure_type=data["failure_type"],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRunManifest:
    session_id: str
    provider_name: str
    runtime_modes: list[BenchmarkRuntimeMode]
    status: BenchmarkStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cases_dir: str = ""
    previous_session_id: str | None = None
    case_results: list[BenchmarkCaseResult] = field(default_factory=list)
    case_comparisons: list[BenchmarkCaseComparison] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _normalize_case_id(self.session_id, "session_id"))
        object.__setattr__(
            self,
            "provider_name",
            _normalize_non_empty_string(self.provider_name, "provider_name"),
        )
        object.__setattr__(
            self,
            "runtime_modes",
            _normalize_runtime_modes(self.runtime_modes, "runtime_modes"),
        )
        object.__setattr__(self, "status", _normalize_enum(self.status, BenchmarkStatus, "status"))
        object.__setattr__(self, "created_at", _normalize_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "cases_dir", _normalize_non_empty_string(self.cases_dir, "cases_dir"))
        object.__setattr__(
            self,
            "previous_session_id",
            _normalize_optional_string(self.previous_session_id, "previous_session_id"),
        )
        object.__setattr__(
            self,
            "case_results",
            _normalize_case_results(self.case_results, "case_results"),
        )
        object.__setattr__(
            self,
            "case_comparisons",
            _normalize_case_comparisons(self.case_comparisons, "case_comparisons"),
        )
        if not self.case_results:
            raise ArgusValidationError("case_results must include at least one item.")
        case_ids = {result.case_id for result in self.case_results}
        comparison_case_ids = {comparison.case_id for comparison in self.case_comparisons}
        unexpected_comparisons = sorted(comparison_case_ids - case_ids)
        if unexpected_comparisons:
            raise ArgusValidationError(
                "case_comparisons reference unknown case_ids: "
                + ", ".join(unexpected_comparisons)
                + "."
            )
        failed_count = self.failed_mode_count + self.failed_case_comparison_count
        if failed_count == 0 and self.status is not BenchmarkStatus.COMPLETED:
            raise ArgusValidationError(
                "status must be completed when all benchmark mode runs and comparisons completed."
            )
        if failed_count > 0 and self.status is not BenchmarkStatus.FAILED:
            raise ArgusValidationError(
                "status must be failed when any benchmark mode run or comparison fails."
            )

    @property
    def case_count(self) -> int:
        return len({result.case_id for result in self.case_results})

    @property
    def mode_result_count(self) -> int:
        return len(self.case_results)

    @property
    def completed_mode_count(self) -> int:
        return sum(result.status is BenchmarkStatus.COMPLETED for result in self.case_results)

    @property
    def failed_mode_count(self) -> int:
        return sum(result.status is BenchmarkStatus.FAILED for result in self.case_results)

    @property
    def completed_case_count(self) -> int:
        return sum(
            all(result.status is BenchmarkStatus.COMPLETED for result in group)
            for group in _group_case_results(self.case_results).values()
        )

    @property
    def failed_case_count(self) -> int:
        return sum(
            any(result.status is BenchmarkStatus.FAILED for result in group)
            for group in _group_case_results(self.case_results).values()
        )

    @property
    def comparison_count(self) -> int:
        return len(self.case_comparisons)

    @property
    def completed_case_comparison_count(self) -> int:
        return sum(
            comparison.status is BenchmarkComparisonStatus.COMPLETED
            for comparison in self.case_comparisons
        )

    @property
    def failed_case_comparison_count(self) -> int:
        return sum(
            comparison.status is BenchmarkComparisonStatus.FAILED
            for comparison in self.case_comparisons
        )

    @property
    def skipped_case_comparison_count(self) -> int:
        return sum(
            comparison.status is BenchmarkComparisonStatus.SKIPPED
            for comparison in self.case_comparisons
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "provider_name": self.provider_name,
            "runtime_modes": [mode.value for mode in self.runtime_modes],
            "status": self.status.value,
            "created_at": _dump_datetime(self.created_at),
            "cases_dir": self.cases_dir,
            "previous_session_id": self.previous_session_id,
            "case_count": self.case_count,
            "mode_result_count": self.mode_result_count,
            "completed_mode_count": self.completed_mode_count,
            "failed_mode_count": self.failed_mode_count,
            "completed_case_count": self.completed_case_count,
            "failed_case_count": self.failed_case_count,
            "comparison_count": self.comparison_count,
            "completed_case_comparison_count": self.completed_case_comparison_count,
            "failed_case_comparison_count": self.failed_case_comparison_count,
            "skipped_case_comparison_count": self.skipped_case_comparison_count,
            "case_results": [result.to_dict() for result in self.case_results],
            "case_comparisons": [comparison.to_dict() for comparison in self.case_comparisons],
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkRunManifest":
        if not isinstance(payload, dict):
            raise ArgusValidationError(
                f"BenchmarkRunManifest must be an object, got {type(payload).__name__}."
            )
        raw_payload = dict(payload)
        raw_payload.setdefault("runtime_modes", [BenchmarkRuntimeMode.ADAPTIVE.value])
        raw_payload.setdefault("case_comparisons", [])
        if "mode_result_count" not in raw_payload and "case_count" in raw_payload:
            raw_payload["mode_result_count"] = raw_payload["case_count"]
        if "completed_mode_count" not in raw_payload and "completed_count" in raw_payload:
            raw_payload["completed_mode_count"] = raw_payload["completed_count"]
        if "failed_mode_count" not in raw_payload and "failed_count" in raw_payload:
            raw_payload["failed_mode_count"] = raw_payload["failed_count"]
        if "completed_case_count" not in raw_payload and "completed_count" in raw_payload:
            raw_payload["completed_case_count"] = raw_payload["completed_count"]
        if "failed_case_count" not in raw_payload and "failed_count" in raw_payload:
            raw_payload["failed_case_count"] = raw_payload["failed_count"]
        raw_payload.setdefault("comparison_count", len(raw_payload["case_comparisons"]))
        raw_payload.setdefault("completed_case_comparison_count", 0)
        raw_payload.setdefault("failed_case_comparison_count", 0)
        raw_payload.setdefault("skipped_case_comparison_count", 0)
        raw_payload.pop("completed_count", None)
        raw_payload.pop("failed_count", None)
        data = _validate_payload_keys(
            raw_payload,
            field_name="BenchmarkRunManifest",
            required={
                "session_id",
                "provider_name",
                "runtime_modes",
                "status",
                "created_at",
                "cases_dir",
                "previous_session_id",
                "case_count",
                "mode_result_count",
                "completed_mode_count",
                "failed_mode_count",
                "completed_case_count",
                "failed_case_count",
                "comparison_count",
                "completed_case_comparison_count",
                "failed_case_comparison_count",
                "skipped_case_comparison_count",
                "case_results",
                "case_comparisons",
            },
        )
        manifest = cls(
            session_id=data["session_id"],
            provider_name=data["provider_name"],
            runtime_modes=data["runtime_modes"],
            status=data["status"],
            created_at=data["created_at"],
            cases_dir=data["cases_dir"],
            previous_session_id=data["previous_session_id"],
            case_results=[
                BenchmarkCaseResult.from_dict(item)
                for item in _normalize_sequence(data["case_results"], "case_results")
            ],
            case_comparisons=[
                BenchmarkCaseComparison.from_dict(item)
                for item in _normalize_sequence(data["case_comparisons"], "case_comparisons")
            ],
        )
        expected_counts = {
            "case_count": manifest.case_count,
            "mode_result_count": manifest.mode_result_count,
            "completed_mode_count": manifest.completed_mode_count,
            "failed_mode_count": manifest.failed_mode_count,
            "completed_case_count": manifest.completed_case_count,
            "failed_case_count": manifest.failed_case_count,
            "comparison_count": manifest.comparison_count,
            "completed_case_comparison_count": manifest.completed_case_comparison_count,
            "failed_case_comparison_count": manifest.failed_case_comparison_count,
            "skipped_case_comparison_count": manifest.skipped_case_comparison_count,
        }
        for field_name, expected in expected_counts.items():
            actual = _normalize_non_negative_int(data[field_name], field_name)
            if actual != expected:
                raise ArgusValidationError(
                    f"{field_name} does not match manifest contents: expected {expected}, got {actual}."
                )
        return manifest


def _normalize_case_id(value: object, field_name: str) -> str:
    normalized = _normalize_non_empty_string(value, field_name)
    if not _CASE_ID_PATTERN.match(normalized):
        raise ArgusValidationError(
            f"{field_name} must match {_CASE_ID_PATTERN.pattern!r}, got {normalized!r}."
        )
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


def _normalize_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_non_empty_string(value, field_name)


def _normalize_string_list(values: object, field_name: str) -> list[str]:
    return [
        _normalize_non_empty_string(value, f"{field_name}[{index}]")
        for index, value in enumerate(_normalize_sequence(values, field_name))
    ]


def _normalize_unique_string_list(values: object, field_name: str) -> list[str]:
    normalized = _normalize_string_list(values, field_name)
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    if duplicates:
        raise ArgusValidationError(
            f"{field_name} contains duplicate values: {', '.join(duplicates)}."
        )
    return normalized


def _normalize_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ArgusValidationError(f"{field_name} must be a positive integer.")
    return value


def _normalize_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArgusValidationError(f"{field_name} must be a non-negative integer.")
    return value


def _normalize_optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ArgusValidationError(
            f"{field_name} must be a boolean or None, got {type(value).__name__}."
        )
    return value


def _normalize_probability(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArgusValidationError(
            f"{field_name} must be a float between 0 and 1 inclusive."
        )
    normalized = float(value)
    if normalized < 0.0 or normalized > 1.0:
        raise ArgusValidationError(
            f"{field_name} must be between 0 and 1 inclusive, got {normalized}."
        )
    return normalized


def _normalize_enum(value: object, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a {enum_type.__name__} or string, "
            f"got {type(value).__name__}."
        )
    try:
        return enum_type(value.strip())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ArgusValidationError(
            f"{field_name} must be one of: {allowed}. Got {value!r}."
        ) from exc


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
            raise ArgusValidationError(f"{field_name} must be a valid ISO-8601 datetime.") from exc
    else:
        raise ArgusValidationError(
            f"{field_name} must be a datetime or ISO-8601 string, got {type(value).__name__}."
        )

    if normalized.tzinfo is None:
        raise ArgusValidationError(f"{field_name} must include timezone information.")
    return normalized.astimezone(timezone.utc)


def _dump_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_case_results(values: object, field_name: str) -> list[BenchmarkCaseResult]:
    normalized: list[BenchmarkCaseResult] = []
    for index, value in enumerate(_normalize_sequence(values, field_name)):
        if not isinstance(value, BenchmarkCaseResult):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a BenchmarkCaseResult, "
                f"got {type(value).__name__}."
            )
        normalized.append(value)
    duplicate_pairs = sorted(
        {
            f"{result.case_id}:{result.runtime_mode.value}"
            for result in normalized
            if sum(
                other.case_id == result.case_id and other.runtime_mode is result.runtime_mode
                for other in normalized
            )
            > 1
        }
    )
    if duplicate_pairs:
        raise ArgusValidationError(
            "case_results contains duplicate case_id/runtime_mode pairs: "
            + ", ".join(duplicate_pairs)
            + "."
        )
    return normalized


def _normalize_mode_judgments(values: object, field_name: str) -> list[BenchmarkModeJudgment]:
    normalized: list[BenchmarkModeJudgment] = []
    for index, value in enumerate(_normalize_sequence(values, field_name)):
        if not isinstance(value, BenchmarkModeJudgment):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a BenchmarkModeJudgment, "
                f"got {type(value).__name__}."
            )
        normalized.append(value)
    duplicates = sorted(
        {
            judgment.runtime_mode.value
            for judgment in normalized
            if sum(other.runtime_mode is judgment.runtime_mode for other in normalized) > 1
        }
    )
    if duplicates:
        raise ArgusValidationError(
            f"{field_name} contains duplicate runtime_mode values: {', '.join(duplicates)}."
        )
    return normalized


def _normalize_optional_benchmark_comparison_assessment(
    value: object,
    field_name: str,
) -> BenchmarkComparisonAssessment | None:
    if value is None:
        return None
    if not isinstance(value, BenchmarkComparisonAssessment):
        raise ArgusValidationError(
            f"{field_name} must be a BenchmarkComparisonAssessment or None, "
            f"got {type(value).__name__}."
        )
    return value


def _normalize_case_comparisons(
    values: object,
    field_name: str,
) -> list[BenchmarkCaseComparison]:
    normalized: list[BenchmarkCaseComparison] = []
    for index, value in enumerate(_normalize_sequence(values, field_name)):
        if not isinstance(value, BenchmarkCaseComparison):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a BenchmarkCaseComparison, "
                f"got {type(value).__name__}."
            )
        normalized.append(value)
    duplicates = sorted(
        {
            comparison.case_id
            for comparison in normalized
            if sum(other.case_id == comparison.case_id for other in normalized) > 1
        }
    )
    if duplicates:
        raise ArgusValidationError(
            f"{field_name} contains duplicate case_id values: {', '.join(duplicates)}."
        )
    return normalized


def _normalize_runtime_modes(values: object, field_name: str) -> list[BenchmarkRuntimeMode]:
    normalized = [
        _normalize_enum(value, BenchmarkRuntimeMode, f"{field_name}[{index}]")
        for index, value in enumerate(_normalize_sequence(values, field_name))
    ]
    if not normalized:
        raise ArgusValidationError(f"{field_name} must include at least one item.")
    duplicates = sorted(
        {mode.value for mode in normalized if normalized.count(mode) > 1}
    )
    if duplicates:
        raise ArgusValidationError(
            f"{field_name} contains duplicate values: {', '.join(duplicates)}."
        )
    return normalized


def _group_case_results(
    case_results: Sequence[BenchmarkCaseResult],
) -> dict[str, list[BenchmarkCaseResult]]:
    grouped: dict[str, list[BenchmarkCaseResult]] = {}
    for result in case_results:
        grouped.setdefault(result.case_id, []).append(result)
    return grouped


def _normalize_sequence(values: object, field_name: str) -> Sequence[object]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(values).__name__}."
        )
    return values


def _validate_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ArgusValidationError(
            f"{field_name} must be an object, got {type(payload).__name__}."
        )
    unknown = sorted(set(payload) - required)
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
