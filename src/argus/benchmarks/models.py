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
class BenchmarkCaseResult:
    case_id: str
    family: BenchmarkFamily
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
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkCaseResult",
            required={
                "case_id",
                "family",
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
    status: BenchmarkStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cases_dir: str = ""
    previous_session_id: str | None = None
    case_results: list[BenchmarkCaseResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _normalize_case_id(self.session_id, "session_id"))
        object.__setattr__(
            self,
            "provider_name",
            _normalize_non_empty_string(self.provider_name, "provider_name"),
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
        if not self.case_results:
            raise ArgusValidationError("case_results must include at least one item.")
        failed_count = self.failed_count
        if failed_count == 0 and self.status is not BenchmarkStatus.COMPLETED:
            raise ArgusValidationError(
                "status must be completed when all benchmark cases completed."
            )
        if failed_count > 0 and self.status is not BenchmarkStatus.FAILED:
            raise ArgusValidationError("status must be failed when any benchmark case fails.")

    @property
    def case_count(self) -> int:
        return len(self.case_results)

    @property
    def completed_count(self) -> int:
        return sum(result.status is BenchmarkStatus.COMPLETED for result in self.case_results)

    @property
    def failed_count(self) -> int:
        return sum(result.status is BenchmarkStatus.FAILED for result in self.case_results)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "provider_name": self.provider_name,
            "status": self.status.value,
            "created_at": _dump_datetime(self.created_at),
            "cases_dir": self.cases_dir,
            "previous_session_id": self.previous_session_id,
            "case_count": self.case_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "case_results": [result.to_dict() for result in self.case_results],
        }

    @classmethod
    def from_dict(cls, payload: object) -> "BenchmarkRunManifest":
        data = _validate_payload_keys(
            payload,
            field_name="BenchmarkRunManifest",
            required={
                "session_id",
                "provider_name",
                "status",
                "created_at",
                "cases_dir",
                "previous_session_id",
                "case_count",
                "completed_count",
                "failed_count",
                "case_results",
            },
        )
        manifest = cls(
            session_id=data["session_id"],
            provider_name=data["provider_name"],
            status=data["status"],
            created_at=data["created_at"],
            cases_dir=data["cases_dir"],
            previous_session_id=data["previous_session_id"],
            case_results=[
                BenchmarkCaseResult.from_dict(item)
                for item in _normalize_sequence(data["case_results"], "case_results")
            ],
        )
        expected_counts = {
            "case_count": manifest.case_count,
            "completed_count": manifest.completed_count,
            "failed_count": manifest.failed_count,
        }
        for field_name, expected in expected_counts.items():
            actual = _normalize_non_negative_int(data[field_name], field_name)
            if actual != expected:
                raise ArgusValidationError(
                    f"{field_name} does not match case_results: expected {expected}, got {actual}."
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
    return normalized


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
