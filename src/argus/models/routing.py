from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from argus.errors import ArgusValidationError


@dataclass(frozen=True, slots=True)
class ProviderRoutingStatsEntry:
    provider_name: str
    action_name: str
    run_count: int = 0
    invocation_count: int = 0
    provider_failure_count: int = 0
    candidate_count: int = 0
    scored_node_count: int = 0
    admitted_count: int = 0
    rejected_count: int = 0
    hard_fail_count: int = 0
    strong_score_count: int = 0
    stress_test_survivor_count: int = 0
    winner_count: int = 0
    winner_contribution_count: int = 0
    critique_count: int = 0
    useful_critique_count: int = 0
    learning_note_count: int = 0
    accumulated_score: float = 0.0
    total_reward: float = 0.0
    last_run_id: str | None = None
    last_updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_name",
            _normalize_non_empty_string(self.provider_name, "provider_name"),
        )
        object.__setattr__(
            self,
            "action_name",
            _normalize_non_empty_string(self.action_name, "action_name"),
        )
        for field_name in (
            "run_count",
            "invocation_count",
            "provider_failure_count",
            "candidate_count",
            "scored_node_count",
            "admitted_count",
            "rejected_count",
            "hard_fail_count",
            "strong_score_count",
            "stress_test_survivor_count",
            "winner_count",
            "winner_contribution_count",
            "critique_count",
            "useful_critique_count",
            "learning_note_count",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_non_negative_int(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "accumulated_score",
            _normalize_non_negative_float(self.accumulated_score, "accumulated_score"),
        )
        object.__setattr__(
            self,
            "total_reward",
            _normalize_float(self.total_reward, "total_reward"),
        )
        if self.last_run_id is not None:
            object.__setattr__(
                self,
                "last_run_id",
                _normalize_non_empty_string(self.last_run_id, "last_run_id"),
            )
        object.__setattr__(
            self,
            "last_updated_at",
            _normalize_datetime(self.last_updated_at, "last_updated_at"),
        )

        if self.provider_failure_count > self.invocation_count:
            raise ArgusValidationError(
                "provider_failure_count must not exceed invocation_count."
            )
        if self.scored_node_count > self.candidate_count:
            raise ArgusValidationError("scored_node_count must not exceed candidate_count.")
        if self.admitted_count + self.rejected_count + self.hard_fail_count > self.candidate_count:
            raise ArgusValidationError(
                "candidate outcome counts must not exceed candidate_count."
            )
        if self.strong_score_count > self.scored_node_count:
            raise ArgusValidationError("strong_score_count must not exceed scored_node_count.")
        if self.useful_critique_count > self.critique_count:
            raise ArgusValidationError("useful_critique_count must not exceed critique_count.")
        if self.winner_count > self.winner_contribution_count:
            raise ArgusValidationError(
                "winner_count must not exceed winner_contribution_count."
            )
        if self.last_run_id is None and any(
            (
                self.run_count,
                self.invocation_count,
                self.candidate_count,
                self.critique_count,
                self.learning_note_count,
            )
        ):
            raise ArgusValidationError("last_run_id must be set when the entry contains data.")

    @property
    def average_reward(self) -> float:
        if self.invocation_count == 0:
            return 0.0
        return self.total_reward / self.invocation_count

    @property
    def average_score(self) -> float:
        if self.scored_node_count == 0:
            return 0.0
        return self.accumulated_score / self.scored_node_count

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_name": self.provider_name,
            "action_name": self.action_name,
            "run_count": self.run_count,
            "invocation_count": self.invocation_count,
            "provider_failure_count": self.provider_failure_count,
            "candidate_count": self.candidate_count,
            "scored_node_count": self.scored_node_count,
            "admitted_count": self.admitted_count,
            "rejected_count": self.rejected_count,
            "hard_fail_count": self.hard_fail_count,
            "strong_score_count": self.strong_score_count,
            "stress_test_survivor_count": self.stress_test_survivor_count,
            "winner_count": self.winner_count,
            "winner_contribution_count": self.winner_contribution_count,
            "critique_count": self.critique_count,
            "useful_critique_count": self.useful_critique_count,
            "learning_note_count": self.learning_note_count,
            "accumulated_score": self.accumulated_score,
            "total_reward": self.total_reward,
            "average_reward": self.average_reward,
            "average_score": self.average_score,
            "last_run_id": self.last_run_id,
            "last_updated_at": _dump_datetime(self.last_updated_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ProviderRoutingStatsEntry":
        data = _validate_payload_keys(
            payload,
            field_name="ProviderRoutingStatsEntry",
            required={
                "provider_name",
                "action_name",
                "run_count",
                "invocation_count",
                "provider_failure_count",
                "candidate_count",
                "scored_node_count",
                "admitted_count",
                "rejected_count",
                "hard_fail_count",
                "strong_score_count",
                "stress_test_survivor_count",
                "winner_count",
                "winner_contribution_count",
                "critique_count",
                "useful_critique_count",
                "learning_note_count",
                "accumulated_score",
                "total_reward",
                "last_run_id",
                "last_updated_at",
            },
            optional={"average_reward", "average_score"},
        )
        return cls(
            provider_name=data["provider_name"],
            action_name=data["action_name"],
            run_count=data["run_count"],
            invocation_count=data["invocation_count"],
            provider_failure_count=data["provider_failure_count"],
            candidate_count=data["candidate_count"],
            scored_node_count=data["scored_node_count"],
            admitted_count=data["admitted_count"],
            rejected_count=data["rejected_count"],
            hard_fail_count=data["hard_fail_count"],
            strong_score_count=data["strong_score_count"],
            stress_test_survivor_count=data["stress_test_survivor_count"],
            winner_count=data["winner_count"],
            winner_contribution_count=data["winner_contribution_count"],
            critique_count=data["critique_count"],
            useful_critique_count=data["useful_critique_count"],
            learning_note_count=data["learning_note_count"],
            accumulated_score=data["accumulated_score"],
            total_reward=data["total_reward"],
            last_run_id=data["last_run_id"],
            last_updated_at=data["last_updated_at"],
        )

    def merge(self, other: "ProviderRoutingStatsEntry") -> "ProviderRoutingStatsEntry":
        if not isinstance(other, ProviderRoutingStatsEntry):
            raise ArgusValidationError(
                "other must be a ProviderRoutingStatsEntry instance, "
                f"got {type(other).__name__}."
            )
        if (self.provider_name, self.action_name) != (other.provider_name, other.action_name):
            raise ArgusValidationError("Cannot merge routing entries with different keys.")
        newer = max(self.last_updated_at, other.last_updated_at)
        last_run_id = other.last_run_id if other.last_updated_at >= self.last_updated_at else self.last_run_id
        return ProviderRoutingStatsEntry(
            provider_name=self.provider_name,
            action_name=self.action_name,
            run_count=self.run_count + other.run_count,
            invocation_count=self.invocation_count + other.invocation_count,
            provider_failure_count=self.provider_failure_count + other.provider_failure_count,
            candidate_count=self.candidate_count + other.candidate_count,
            scored_node_count=self.scored_node_count + other.scored_node_count,
            admitted_count=self.admitted_count + other.admitted_count,
            rejected_count=self.rejected_count + other.rejected_count,
            hard_fail_count=self.hard_fail_count + other.hard_fail_count,
            strong_score_count=self.strong_score_count + other.strong_score_count,
            stress_test_survivor_count=(
                self.stress_test_survivor_count + other.stress_test_survivor_count
            ),
            winner_count=self.winner_count + other.winner_count,
            winner_contribution_count=(
                self.winner_contribution_count + other.winner_contribution_count
            ),
            critique_count=self.critique_count + other.critique_count,
            useful_critique_count=self.useful_critique_count + other.useful_critique_count,
            learning_note_count=self.learning_note_count + other.learning_note_count,
            accumulated_score=self.accumulated_score + other.accumulated_score,
            total_reward=self.total_reward + other.total_reward,
            last_run_id=last_run_id,
            last_updated_at=newer,
        )


@dataclass(frozen=True, slots=True)
class ProviderRoutingStats:
    entries: list[ProviderRoutingStatsEntry] = field(default_factory=list)
    schema_version: int = 1
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "entries",
            _normalize_entries(self.entries, "entries"),
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

        seen: set[tuple[str, str]] = set()
        for entry in self.entries:
            key = (entry.provider_name, entry.action_name)
            if key in seen:
                raise ArgusValidationError(
                    "entries must not contain duplicate provider/action pairs."
                )
            seen.add(key)

    def to_dict(self) -> dict[str, object]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "schema_version": self.schema_version,
            "updated_at": _dump_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: object) -> "ProviderRoutingStats":
        data = _validate_payload_keys(
            payload,
            field_name="ProviderRoutingStats",
            required={"entries", "schema_version", "updated_at"},
        )
        return cls(
            entries=[
                ProviderRoutingStatsEntry.from_dict(item)
                for item in _normalize_sequence(data["entries"], "entries")
            ],
            schema_version=data["schema_version"],
            updated_at=data["updated_at"],
        )

    @classmethod
    def empty(cls) -> "ProviderRoutingStats":
        return cls(entries=[])

    def merge(self, other: "ProviderRoutingStats") -> "ProviderRoutingStats":
        if not isinstance(other, ProviderRoutingStats):
            raise ArgusValidationError(
                "other must be a ProviderRoutingStats instance, "
                f"got {type(other).__name__}."
            )
        if not self.entries:
            return other
        if not other.entries:
            return self
        merged: dict[tuple[str, str], ProviderRoutingStatsEntry] = {
            (entry.provider_name, entry.action_name): entry for entry in self.entries
        }
        for entry in other.entries:
            key = (entry.provider_name, entry.action_name)
            if key in merged:
                merged[key] = merged[key].merge(entry)
            else:
                merged[key] = entry
        return ProviderRoutingStats(
            entries=sorted(
                merged.values(),
                key=lambda item: (item.provider_name, item.action_name),
            ),
            schema_version=max(self.schema_version, other.schema_version),
            updated_at=max(self.updated_at, other.updated_at),
        )


def _normalize_entries(value: object, field_name: str) -> list[ProviderRoutingStatsEntry]:
    normalized = _normalize_sequence(value, field_name)
    entries: list[ProviderRoutingStatsEntry] = []
    for index, item in enumerate(normalized):
        if not isinstance(item, ProviderRoutingStatsEntry):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a ProviderRoutingStatsEntry instance, "
                f"got {type(item).__name__}."
            )
        entries.append(item)
    return entries


def _normalize_sequence(value: object, field_name: str) -> list[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ArgusValidationError(
            f"{field_name} must be a list, got {type(value).__name__}."
        )
    return list(value)


def _validate_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ArgusValidationError(
            f"{field_name} payload must be a mapping, got {type(payload).__name__}."
        )
    optional_keys = optional or set()
    keys = set(payload)
    missing = required - keys
    unexpected = keys - required - optional_keys
    if missing:
        joined = ", ".join(sorted(missing))
        raise ArgusValidationError(f"{field_name} payload is missing required keys: {joined}.")
    if unexpected:
        joined = ", ".join(sorted(unexpected))
        raise ArgusValidationError(
            f"{field_name} payload contains unexpected keys: {joined}."
        )
    return dict(payload)


def _normalize_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _normalize_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise ArgusValidationError(
            f"{field_name} must be an integer, got {type(value).__name__}."
        )
    if value < 0:
        raise ArgusValidationError(f"{field_name} must be non-negative.")
    return value


def _normalize_positive_int(value: object, field_name: str) -> int:
    normalized = _normalize_non_negative_int(value, field_name)
    if normalized <= 0:
        raise ArgusValidationError(f"{field_name} must be positive.")
    return normalized


def _normalize_float(value: object, field_name: str) -> float:
    if not isinstance(value, int | float):
        raise ArgusValidationError(
            f"{field_name} must be a finite number, got {type(value).__name__}."
        )
    normalized = float(value)
    if normalized != normalized or normalized in {float("inf"), float("-inf")}:
        raise ArgusValidationError(f"{field_name} must be finite.")
    return normalized


def _normalize_non_negative_float(value: object, field_name: str) -> float:
    normalized = _normalize_float(value, field_name)
    if normalized < 0.0:
        raise ArgusValidationError(f"{field_name} must be non-negative.")
    return normalized


def _normalize_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            normalized = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ArgusValidationError(
                f"{field_name} must be an ISO 8601 timestamp, got {value!r}."
            ) from exc
    elif isinstance(value, datetime):
        normalized = value
    else:
        raise ArgusValidationError(
            f"{field_name} must be a datetime or ISO string, got {type(value).__name__}."
        )
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc)


def _dump_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
