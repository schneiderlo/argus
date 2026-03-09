from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
import math
from pathlib import Path
import shutil

from argus.errors import ArgusUserError, ArgusValidationError
from argus.models import (
    FinalRecommendation,
    JSONValue,
    LearningMemory,
    LearningNote,
    Node,
    OutcomeFeedback,
    OutcomeFeedbackLedger,
    ProblemSpec,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    ResearchArtifactBundle,
    SearchIsland,
    SearchState,
)


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    provider_name: str
    budget: int
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = 1
    problem_spec_path: str = "problem-spec.json"
    state_path: str | None = None
    learning_notes_path: str | None = None
    reusable_learning_path: str | None = None
    outcome_feedback_path: str | None = None
    final_recommendation_path: str | None = None
    summary_path: str | None = None
    research_bundle_path: str | None = None
    research_artifacts_dir: str | None = None
    nodes_dir: str = "nodes"
    scores_dir: str = "scores"
    critiques_dir: str = "critiques"
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _normalize_path_segment(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "provider_name",
            _normalize_non_empty_string(self.provider_name, "provider_name"),
        )
        object.__setattr__(self, "budget", _normalize_positive_int(self.budget, "budget"))
        object.__setattr__(self, "status", _normalize_enum(self.status, RunStatus, "status"))
        object.__setattr__(
            self,
            "created_at",
            _normalize_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _normalize_datetime(self.updated_at, "updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ArgusValidationError("updated_at must not be earlier than created_at.")
        object.__setattr__(
            self,
            "schema_version",
            _normalize_positive_int(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "problem_spec_path",
            _normalize_relative_path(self.problem_spec_path, "problem_spec_path"),
        )
        object.__setattr__(
            self,
            "state_path",
            _normalize_optional_relative_path(self.state_path, "state_path"),
        )
        object.__setattr__(
            self,
            "learning_notes_path",
            _normalize_optional_relative_path(
                self.learning_notes_path,
                "learning_notes_path",
            ),
        )
        object.__setattr__(
            self,
            "reusable_learning_path",
            _normalize_optional_relative_path(
                self.reusable_learning_path,
                "reusable_learning_path",
            ),
        )
        object.__setattr__(
            self,
            "outcome_feedback_path",
            _normalize_optional_relative_path(
                self.outcome_feedback_path,
                "outcome_feedback_path",
            ),
        )
        object.__setattr__(
            self,
            "final_recommendation_path",
            _normalize_optional_relative_path(
                self.final_recommendation_path,
                "final_recommendation_path",
            ),
        )
        object.__setattr__(
            self,
            "summary_path",
            _normalize_optional_relative_path(self.summary_path, "summary_path"),
        )
        object.__setattr__(
            self,
            "research_bundle_path",
            _normalize_optional_relative_path(
                self.research_bundle_path,
                "research_bundle_path",
            ),
        )
        object.__setattr__(
            self,
            "research_artifacts_dir",
            _normalize_optional_relative_path(
                self.research_artifacts_dir,
                "research_artifacts_dir",
            ),
        )
        object.__setattr__(self, "nodes_dir", _normalize_relative_path(self.nodes_dir, "nodes_dir"))
        object.__setattr__(self, "scores_dir", _normalize_relative_path(self.scores_dir, "scores_dir"))
        object.__setattr__(
            self,
            "critiques_dir",
            _normalize_relative_path(self.critiques_dir, "critiques_dir"),
        )
        object.__setattr__(self, "metadata", _normalize_json_object(self.metadata, "metadata"))
        object.__setattr__(self, "error", _normalize_optional_string(self.error, "error"))
        if self.status is RunStatus.FAILED and self.error is None:
            raise ArgusValidationError("error must be set when status is failed.")

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "provider_name": self.provider_name,
            "budget": self.budget,
            "status": self.status.value,
            "created_at": _dump_datetime(self.created_at),
            "updated_at": _dump_datetime(self.updated_at),
            "schema_version": self.schema_version,
            "problem_spec_path": self.problem_spec_path,
            "state_path": self.state_path,
            "learning_notes_path": self.learning_notes_path,
            "reusable_learning_path": self.reusable_learning_path,
            "outcome_feedback_path": self.outcome_feedback_path,
            "final_recommendation_path": self.final_recommendation_path,
            "summary_path": self.summary_path,
            "research_bundle_path": self.research_bundle_path,
            "research_artifacts_dir": self.research_artifacts_dir,
            "nodes_dir": self.nodes_dir,
            "scores_dir": self.scores_dir,
            "critiques_dir": self.critiques_dir,
            "metadata": _copy_json_object(self.metadata),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "RunManifest":
        data = _validate_payload_keys(
            payload,
            field_name="RunManifest",
            required={
                "run_id",
                "provider_name",
                "budget",
                "status",
                "created_at",
                "updated_at",
                "schema_version",
                "problem_spec_path",
                "state_path",
                "learning_notes_path",
                "final_recommendation_path",
                "summary_path",
                "nodes_dir",
                "scores_dir",
                "critiques_dir",
                "metadata",
                "error",
            },
            optional={
                "reusable_learning_path",
                "outcome_feedback_path",
                "research_bundle_path",
                "research_artifacts_dir",
            },
        )
        return cls(
            run_id=data["run_id"],
            provider_name=data["provider_name"],
            budget=data["budget"],
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            schema_version=data["schema_version"],
            problem_spec_path=data["problem_spec_path"],
            state_path=data["state_path"],
            learning_notes_path=data["learning_notes_path"],
            reusable_learning_path=data.get("reusable_learning_path"),
            outcome_feedback_path=data.get("outcome_feedback_path"),
            final_recommendation_path=data["final_recommendation_path"],
            summary_path=data["summary_path"],
            research_bundle_path=data.get("research_bundle_path"),
            research_artifacts_dir=data.get("research_artifacts_dir"),
            nodes_dir=data["nodes_dir"],
            scores_dir=data["scores_dir"],
            critiques_dir=data["critiques_dir"],
            metadata=data["metadata"],
            error=data["error"],
        )


@dataclass(frozen=True, slots=True)
class StateIndex:
    root_id: str
    node_ids: list[str]
    archive_ids: list[str] = field(default_factory=list)
    frontier_ids: list[str] = field(default_factory=list)
    pruned_ids: list[str] = field(default_factory=list)
    winner_ids: list[str] = field(default_factory=list)
    islands: dict[str, SearchIsland] = field(default_factory=dict)
    budget_spent: int = 0
    step_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_id", _normalize_non_empty_string(self.root_id, "root_id"))
        object.__setattr__(self, "node_ids", _normalize_unique_string_list(self.node_ids, "node_ids"))
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
        object.__setattr__(
            self,
            "winner_ids",
            _normalize_unique_string_list(self.winner_ids, "winner_ids"),
        )
        object.__setattr__(self, "islands", _normalize_search_island_map(self.islands))
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

        node_ids = set(self.node_ids)
        if self.root_id not in node_ids:
            raise ArgusValidationError(
                f"root_id must exist in node_ids, got {self.root_id!r}."
            )

        for field_name, values in (
            ("archive_ids", self.archive_ids),
            ("frontier_ids", self.frontier_ids),
            ("pruned_ids", self.pruned_ids),
            ("winner_ids", self.winner_ids),
        ):
            unknown_ids = [node_id for node_id in values if node_id not in node_ids]
            if unknown_ids:
                joined = ", ".join(sorted(unknown_ids))
                raise ArgusValidationError(
                    f"{field_name} contains unknown node ids: {joined}."
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "root_id": self.root_id,
            "node_ids": list(self.node_ids),
            "archive_ids": list(self.archive_ids),
            "frontier_ids": list(self.frontier_ids),
            "pruned_ids": list(self.pruned_ids),
            "winner_ids": list(self.winner_ids),
            "islands": {
                island_id: self.islands[island_id].to_dict()
                for island_id in sorted(self.islands)
            },
            "budget_spent": self.budget_spent,
            "step_count": self.step_count,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "StateIndex":
        data = _validate_payload_keys(
            payload,
            field_name="StateIndex",
            required={
                "root_id",
                "node_ids",
                "archive_ids",
                "frontier_ids",
                "pruned_ids",
                "winner_ids",
                "budget_spent",
                "step_count",
            },
            optional={"islands"},
        )
        return cls(
            root_id=data["root_id"],
            node_ids=data["node_ids"],
            archive_ids=data["archive_ids"],
            frontier_ids=data["frontier_ids"],
            pruned_ids=data["pruned_ids"],
            winner_ids=data["winner_ids"],
            islands={
                island_id: SearchIsland.from_dict(island_payload)
                for island_id, island_payload in sorted(
                    _normalize_mapping(data.get("islands", {}), "islands").items()
                )
            },
            budget_spent=data["budget_spent"],
            step_count=data["step_count"],
        )

    @classmethod
    def from_search_state(cls, state: SearchState) -> "StateIndex":
        return cls(
            root_id=state.root_id,
            node_ids=sorted(state.nodes),
            archive_ids=state.archive_ids,
            frontier_ids=state.frontier_ids,
            pruned_ids=state.pruned_ids,
            winner_ids=state.winner_ids,
            islands=state.islands,
            budget_spent=state.budget_spent,
            step_count=state.step_count,
        )


@dataclass(frozen=True, slots=True)
class PersistedRun:
    path: Path
    manifest: RunManifest
    problem_spec: ProblemSpec
    state: SearchState | None = None
    reusable_learning_context: LearningMemory | None = None
    outcome_feedback: OutcomeFeedbackLedger | None = None
    final_recommendation: FinalRecommendation | None = None
    summary_markdown: str | None = None
    research_bundle: ResearchArtifactBundle | None = None
    routing_summary: ProviderRoutingStats | None = None


class FileSystemStateStore:
    _LEARNING_MEMORY_PATH = "learning-memory.json"
    _OUTCOME_FEEDBACK_LEDGER_PATH = "outcome-feedback-ledger.json"
    _ROUTING_SUMMARY_PATH = "routing-summary.json"
    _ROUTING_STATS_PATH = "provider-routing-stats.json"
    _PROGRESS_EVENTS_PATH = "progress-events.jsonl"

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.expanduser().resolve()

    def allocate_run_id(self, *, timestamp: datetime | None = None) -> str:
        normalized_timestamp = _normalize_datetime(
            datetime.now(timezone.utc) if timestamp is None else timestamp,
            "timestamp",
        )
        return self._allocate_run_id(None, normalized_timestamp)

    def progress_events_path(self, run_id: str) -> Path:
        return self.root_dir / _normalize_path_segment(run_id, "run_id") / self._PROGRESS_EVENTS_PATH

    def load_progress_events(
        self,
        run_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        normalized_run_id = _normalize_path_segment(run_id, "run_id")
        manifest, run_dir = self._load_manifest(normalized_run_id)
        path = run_dir / self._PROGRESS_EVENTS_PATH
        if not path.is_file():
            return []

        limit_count = None if limit is None else max(0, int(limit))
        events: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ArgusValidationError(
                        f"Invalid progress event JSON in {path}: {exc}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ArgusValidationError(
                        f"Invalid progress event payload in {path}: not an object."
                    )
                run_id_value = payload.get("run_id")
                if run_id_value != manifest.run_id:
                    continue
                events.append(dict(payload))
        if limit_count is None:
            return events
        if limit_count <= 0:
            return []
        return events[-limit_count:]

    def create_run(
        self,
        *,
        problem_spec: ProblemSpec,
        provider_name: str,
        budget: int,
        run_id: str | None = None,
        created_at: datetime | None = None,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> RunManifest:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )

        timestamp = _normalize_datetime(created_at or datetime.now(timezone.utc), "created_at")
        normalized_run_id = self._allocate_run_id(run_id, timestamp)
        run_dir = self.root_dir / normalized_run_id
        if run_dir.exists():
            raise ArgusUserError(f"Run already exists: {normalized_run_id}")

        self.root_dir.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=False)

        manifest = RunManifest(
            run_id=normalized_run_id,
            provider_name=provider_name,
            budget=budget,
            created_at=timestamp,
            updated_at=timestamp,
            metadata={} if metadata is None else dict(metadata),
        )
        self._ensure_run_layout(run_dir, manifest)
        self._write_json(run_dir / manifest.problem_spec_path, problem_spec.to_dict())
        self._write_manifest(run_dir, manifest)
        return manifest

    def save_snapshot(
        self,
        run_id: str,
        *,
        state: SearchState,
        research_bundle: ResearchArtifactBundle | None = None,
        research_markdown: Mapping[str, str] | None = None,
        final_recommendation: FinalRecommendation | None = None,
        summary_markdown: str | None = None,
        routing_summary: ProviderRoutingStats | None = None,
        status: RunStatus = RunStatus.RUNNING,
        updated_at: datetime | None = None,
        metadata_patch: Mapping[str, JSONValue] | None = None,
        error: str | None = None,
    ) -> RunManifest:
        if not isinstance(state, SearchState):
            raise ArgusValidationError(
                f"state must be a SearchState instance, got {type(state).__name__}."
            )

        normalized_run_id = _normalize_path_segment(run_id, "run_id")
        manifest, run_dir = self._load_manifest(normalized_run_id)
        self._ensure_run_layout(run_dir, manifest)

        index = StateIndex.from_search_state(state)
        if final_recommendation is not None:
            self._validate_final_recommendation(final_recommendation, state)
        if research_bundle is not None and not isinstance(research_bundle, ResearchArtifactBundle):
            raise ArgusValidationError(
                "research_bundle must be a ResearchArtifactBundle instance or None, "
                f"got {type(research_bundle).__name__}."
            )

        self._write_json(run_dir / manifest.problem_spec_path, state.problem_spec.to_dict())
        self._sync_nodes(run_dir, manifest, state.nodes)

        state_path = "state.json"
        learning_notes_path = "learning-notes.json"
        self._write_json(run_dir / state_path, index.to_dict())
        self._write_json(
            run_dir / learning_notes_path,
            [note.to_dict() for note in state.learning_notes],
        )

        final_recommendation_path = self._write_optional_json(
            run_dir,
            "final-recommendation.json",
            None if final_recommendation is None else final_recommendation.to_dict(),
        )
        summary_path = self._write_optional_text(run_dir, "summary.md", summary_markdown)
        research_bundle_path = self._write_optional_json(
            run_dir,
            "research/bundle.json",
            None if research_bundle is None else research_bundle.to_dict(),
        )
        research_artifacts_dir = self._write_research_markdown(
            run_dir,
            "research/markdown",
            research_markdown,
        )
        if routing_summary is None:
            routing_summary_path = run_dir / self._ROUTING_SUMMARY_PATH
            if routing_summary_path.exists():
                routing_summary_path.unlink()
        else:
            self._write_json(
                run_dir / self._ROUTING_SUMMARY_PATH,
                routing_summary.to_dict(),
            )

        merged_metadata = dict(manifest.metadata)
        if metadata_patch is not None:
            merged_metadata.update(metadata_patch)

        normalized_error = _normalize_optional_string(error, "error")
        normalized_status = _normalize_enum(status, RunStatus, "status")
        if normalized_status is RunStatus.FAILED and normalized_error is None:
            raise ArgusValidationError("error must be set when status is failed.")
        if normalized_status is not RunStatus.FAILED:
            normalized_error = None

        new_updated_at = updated_at or datetime.now(timezone.utc)
        if new_updated_at < manifest.updated_at:
            new_updated_at = manifest.updated_at

        refreshed_manifest = replace(
            manifest,
            status=normalized_status,
            updated_at=_normalize_datetime(new_updated_at, "updated_at"),
            state_path=state_path,
            learning_notes_path=learning_notes_path,
            final_recommendation_path=final_recommendation_path,
            summary_path=summary_path,
            research_bundle_path=research_bundle_path,
            research_artifacts_dir=research_artifacts_dir,
            metadata=merged_metadata,
            error=normalized_error,
        )
        self._write_manifest(run_dir, refreshed_manifest)
        return refreshed_manifest

    def save_reusable_learning_context(
        self,
        run_id: str,
        memory: LearningMemory | None,
        *,
        updated_at: datetime | None = None,
    ) -> RunManifest:
        if memory is not None and not isinstance(memory, LearningMemory):
            raise ArgusValidationError(
                "memory must be a LearningMemory instance or None, "
                f"got {type(memory).__name__}."
            )
        normalized_run_id = _normalize_path_segment(run_id, "run_id")
        manifest, run_dir = self._load_manifest(normalized_run_id)
        reusable_learning_path = self._write_optional_json(
            run_dir,
            "reusable-learning-context.json",
            None if memory is None or not memory.entries else memory.to_dict(),
        )
        new_updated_at = updated_at or datetime.now(timezone.utc)
        if new_updated_at < manifest.updated_at:
            new_updated_at = manifest.updated_at

        refreshed_manifest = replace(
            manifest,
            updated_at=_normalize_datetime(
                new_updated_at,
                "updated_at",
            ),
            reusable_learning_path=reusable_learning_path,
        )
        self._write_manifest(run_dir, refreshed_manifest)
        return refreshed_manifest

    def load_run(self, run_id: str) -> PersistedRun:
        normalized_run_id = _normalize_path_segment(run_id, "run_id")
        manifest, run_dir = self._load_manifest(normalized_run_id)
        problem_spec = ProblemSpec.from_dict(
            self._read_json_required(run_dir / manifest.problem_spec_path)
        )
        state = self._load_state(run_dir, manifest, problem_spec)
        reusable_learning_context: LearningMemory | None = None
        if manifest.reusable_learning_path is not None:
            reusable_learning_context = LearningMemory.from_dict(
                self._read_json_required(run_dir / manifest.reusable_learning_path)
            )
        outcome_feedback: OutcomeFeedbackLedger | None = None
        if manifest.outcome_feedback_path is not None:
            outcome_feedback = OutcomeFeedbackLedger.from_dict(
                self._read_json_required(run_dir / manifest.outcome_feedback_path)
            )
        final_recommendation: FinalRecommendation | None = None
        if manifest.final_recommendation_path is not None:
            if state is None:
                raise ArgusValidationError(
                    "final_recommendation_path is set but no state snapshot is present."
                )
            final_recommendation = FinalRecommendation.from_dict(
                self._read_json_required(run_dir / manifest.final_recommendation_path)
            )
            self._validate_final_recommendation(final_recommendation, state)

        summary_markdown: str | None = None
        if manifest.summary_path is not None:
            summary_path = run_dir / manifest.summary_path
            if not summary_path.is_file():
                raise ArgusValidationError(f"Missing summary file: {summary_path}")
            summary_markdown = summary_path.read_text(encoding="utf-8")

        research_bundle: ResearchArtifactBundle | None = None
        if manifest.research_bundle_path is not None:
            research_bundle = ResearchArtifactBundle.from_dict(
                self._read_json_required(run_dir / manifest.research_bundle_path)
            )

        routing_summary: ProviderRoutingStats | None = None
        routing_summary_path = run_dir / self._ROUTING_SUMMARY_PATH
        if routing_summary_path.is_file():
            routing_summary = ProviderRoutingStats.from_dict(
                self._read_json_required(routing_summary_path)
            )

        return PersistedRun(
            path=run_dir,
            manifest=manifest,
            problem_spec=problem_spec,
            state=state,
            reusable_learning_context=reusable_learning_context,
            outcome_feedback=outcome_feedback,
            final_recommendation=final_recommendation,
            summary_markdown=summary_markdown,
            research_bundle=research_bundle,
            routing_summary=routing_summary,
        )

    def list_runs(self) -> list[RunManifest]:
        if not self.root_dir.is_dir():
            return []

        manifests: list[RunManifest] = []
        for run_dir in sorted(path for path in self.root_dir.iterdir() if path.is_dir()):
            manifest_path = run_dir / "run.json"
            if not manifest_path.is_file():
                continue
            manifests.append(RunManifest.from_dict(self._read_json_required(manifest_path)))
        return manifests

    def update_manifest_status(
        self,
        run_id: str,
        *,
        status: RunStatus,
        updated_at: datetime | None = None,
        metadata_patch: Mapping[str, JSONValue] | None = None,
        error: str | None = None,
    ) -> RunManifest:
        normalized_run_id = _normalize_path_segment(run_id, "run_id")
        manifest, run_dir = self._load_manifest(normalized_run_id)
        merged_metadata = dict(manifest.metadata)
        if metadata_patch is not None:
            merged_metadata.update(metadata_patch)

        normalized_error = _normalize_optional_string(error, "error")
        normalized_status = _normalize_enum(status, RunStatus, "status")
        if normalized_status is RunStatus.FAILED and normalized_error is None:
            raise ArgusValidationError("error must be set when status is failed.")
        if normalized_status is not RunStatus.FAILED:
            normalized_error = None

        new_updated_at = updated_at or datetime.now(timezone.utc)
        if new_updated_at < manifest.updated_at:
            new_updated_at = manifest.updated_at

        refreshed_manifest = replace(
            manifest,
            status=normalized_status,
            updated_at=_normalize_datetime(new_updated_at, "updated_at"),
            metadata=merged_metadata,
            error=normalized_error,
        )
        self._write_manifest(run_dir, refreshed_manifest)
        return refreshed_manifest

    def save_provider_routing_summary(
        self,
        run_id: str,
        summary: ProviderRoutingStats,
    ) -> ProviderRoutingStats:
        if not isinstance(summary, ProviderRoutingStats):
            raise ArgusValidationError(
                "summary must be a ProviderRoutingStats instance, "
                f"got {type(summary).__name__}."
            )
        normalized_run_id = _normalize_path_segment(run_id, "run_id")
        _, run_dir = self._load_manifest(normalized_run_id)
        self._write_json(run_dir / self._ROUTING_SUMMARY_PATH, summary.to_dict())
        return summary

    def load_provider_routing_stats(self) -> ProviderRoutingStats:
        path = self.root_dir / self._ROUTING_STATS_PATH
        if not path.is_file():
            return ProviderRoutingStats.empty()
        return ProviderRoutingStats.from_dict(self._read_json_required(path))

    def load_learning_memory(self) -> LearningMemory:
        path = self.root_dir / self._LEARNING_MEMORY_PATH
        if not path.is_file():
            return LearningMemory.empty()
        return LearningMemory.from_dict(self._read_json_required(path))

    def load_outcome_feedback_ledger(self) -> OutcomeFeedbackLedger:
        path = self.root_dir / self._OUTCOME_FEEDBACK_LEDGER_PATH
        if not path.is_file():
            return OutcomeFeedbackLedger.empty()
        return OutcomeFeedbackLedger.from_dict(self._read_json_required(path))

    def save_learning_memory(self, memory: LearningMemory) -> LearningMemory:
        if not isinstance(memory, LearningMemory):
            raise ArgusValidationError(
                "memory must be a LearningMemory instance, "
                f"got {type(memory).__name__}."
            )
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.root_dir / self._LEARNING_MEMORY_PATH, memory.to_dict())
        return memory

    def save_outcome_feedback_ledger(
        self,
        ledger: OutcomeFeedbackLedger,
    ) -> OutcomeFeedbackLedger:
        if not isinstance(ledger, OutcomeFeedbackLedger):
            raise ArgusValidationError(
                "ledger must be an OutcomeFeedbackLedger instance, "
                f"got {type(ledger).__name__}."
            )
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.root_dir / self._OUTCOME_FEEDBACK_LEDGER_PATH, ledger.to_dict())
        return ledger

    def merge_learning_memory(
        self,
        *,
        run_id: str,
        problem_spec: ProblemSpec,
        notes: Sequence[LearningNote],
        updated_at: datetime | None = None,
    ) -> LearningMemory:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        normalized_notes = _normalize_learning_notes(notes, "notes")
        if not normalized_notes:
            return self.load_learning_memory()
        merged = self.load_learning_memory().merge_observations(
            run_id=_normalize_non_empty_string(run_id, "run_id"),
            problem_spec=problem_spec,
            notes=normalized_notes,
            observed_at=updated_at,
        )
        return self.save_learning_memory(merged)

    def record_outcome_feedback(
        self,
        feedback: OutcomeFeedback,
    ) -> tuple[RunManifest, OutcomeFeedbackLedger, LearningMemory]:
        if not isinstance(feedback, OutcomeFeedback):
            raise ArgusValidationError(
                "feedback must be an OutcomeFeedback instance, "
                f"got {type(feedback).__name__}."
            )
        persisted_run = self.load_run(feedback.run_id)
        if persisted_run.state is None:
            raise ArgusValidationError(
                f"Run {feedback.run_id!r} has no persisted state to attach feedback to."
            )
        if feedback.node_id not in persisted_run.state.nodes:
            raise ArgusValidationError(
                f"Run {feedback.run_id!r} does not contain node {feedback.node_id!r}."
            )
        node = persisted_run.state.nodes[feedback.node_id]
        if node.candidate.thesis != feedback.candidate_thesis:
            raise ArgusValidationError(
                "feedback candidate_thesis must match the persisted node thesis."
            )
        if persisted_run.problem_spec.request != feedback.problem_statement:
            raise ArgusValidationError(
                "feedback problem_statement must match the persisted run problem."
            )

        manifest, run_dir = self._load_manifest(feedback.run_id)
        run_feedback = (
            OutcomeFeedbackLedger.empty()
            if persisted_run.outcome_feedback is None
            else persisted_run.outcome_feedback
        ).append(feedback)
        outcome_feedback_path = self._write_optional_json(
            run_dir,
            "outcome-feedback.json",
            run_feedback.to_dict(),
        )

        merged_metadata = dict(manifest.metadata)
        merged_metadata.update(
            {
                "last_outcome_feedback_id": feedback.feedback_id,
                "last_outcome_status": feedback.outcome_status.value,
                "outcome_feedback_count": len(run_feedback.entries),
            }
        )
        refreshed_manifest = replace(
            manifest,
            updated_at=max(manifest.updated_at, feedback.recorded_at),
            outcome_feedback_path=outcome_feedback_path,
            metadata=merged_metadata,
        )
        self._write_manifest(run_dir, refreshed_manifest)

        aggregate_feedback = self.save_outcome_feedback_ledger(
            self.load_outcome_feedback_ledger().append(feedback)
        )
        merged_memory = self.save_learning_memory(
            self.load_learning_memory().merge_outcome_feedback(feedback)
        )
        routing_feedback = _feedback_routing_summary(node=node, feedback=feedback)
        if routing_feedback.entries:
            run_routing_summary = (
                routing_feedback
                if persisted_run.routing_summary is None
                else persisted_run.routing_summary.merge(routing_feedback)
            )
            self.save_provider_routing_summary(feedback.run_id, run_routing_summary)
            self.merge_provider_routing_stats(routing_feedback)
        return refreshed_manifest, aggregate_feedback, merged_memory

    def merge_provider_routing_stats(
        self,
        summary: ProviderRoutingStats,
    ) -> ProviderRoutingStats:
        if not isinstance(summary, ProviderRoutingStats):
            raise ArgusValidationError(
                "summary must be a ProviderRoutingStats instance, "
                f"got {type(summary).__name__}."
            )
        self.root_dir.mkdir(parents=True, exist_ok=True)
        merged = self.load_provider_routing_stats().merge(summary)
        self._write_json(self.root_dir / self._ROUTING_STATS_PATH, merged.to_dict())
        return merged

    def _allocate_run_id(self, run_id: str | None, timestamp: datetime) -> str:
        if run_id is not None:
            return _normalize_path_segment(run_id, "run_id")

        base = timestamp.strftime("run-%Y%m%dT%H%M%SZ")
        candidate = base
        index = 1
        while (self.root_dir / candidate).exists():
            candidate = f"{base}-{index:02d}"
            index += 1
        return candidate

    def _load_manifest(self, run_id: str) -> tuple[RunManifest, Path]:
        run_dir = self.root_dir / run_id
        manifest_path = run_dir / "run.json"
        if not manifest_path.is_file():
            raise ArgusUserError(f"Run does not exist: {run_id}")
        manifest = RunManifest.from_dict(self._read_json_required(manifest_path))
        if manifest.run_id != run_id:
            raise ArgusValidationError(
                f"Manifest run_id {manifest.run_id!r} does not match directory {run_id!r}."
            )
        return manifest, run_dir

    def _load_state(
        self,
        run_dir: Path,
        manifest: RunManifest,
        problem_spec: ProblemSpec,
    ) -> SearchState | None:
        if manifest.state_path is None:
            return None
        if manifest.learning_notes_path is None:
            raise ArgusValidationError(
                "learning_notes_path must be set when state_path is present."
            )

        index = StateIndex.from_dict(self._read_json_required(run_dir / manifest.state_path))
        node_ids = set(index.node_ids)
        nodes_dir = run_dir / manifest.nodes_dir
        scores_dir = run_dir / manifest.scores_dir
        critiques_dir = run_dir / manifest.critiques_dir

        existing_node_ids = _json_file_stems(nodes_dir)
        if existing_node_ids != node_ids:
            missing = sorted(node_ids - existing_node_ids)
            extra = sorted(existing_node_ids - node_ids)
            details: list[str] = []
            if missing:
                details.append(f"missing node files: {', '.join(missing)}")
            if extra:
                details.append(f"unexpected node files: {', '.join(extra)}")
            raise ArgusValidationError(
                "State snapshot does not match nodes directory: " + "; ".join(details)
            )

        extra_score_ids = _json_file_stems(scores_dir) - node_ids
        if extra_score_ids:
            joined = ", ".join(sorted(extra_score_ids))
            raise ArgusValidationError(
                f"Scores directory contains files for unknown nodes: {joined}."
            )

        extra_critique_ids = _json_file_stems(critiques_dir) - node_ids
        if extra_critique_ids:
            joined = ", ".join(sorted(extra_critique_ids))
            raise ArgusValidationError(
                f"Critiques directory contains files for unknown nodes: {joined}."
            )

        score_ids = _json_file_stems(scores_dir)
        critique_ids = _json_file_stems(critiques_dir)
        nodes: dict[str, Node] = {}
        for node_id in index.node_ids:
            raw_payload = self._read_json_required(nodes_dir / f"{node_id}.json")
            if not isinstance(raw_payload, Mapping):
                raise ArgusValidationError(
                    f"Node file must contain an object, got {type(raw_payload).__name__}."
                )
            payload = dict(raw_payload)
            if node_id in score_ids:
                payload["score"] = self._read_json_required(scores_dir / f"{node_id}.json")
            if node_id in critique_ids:
                payload["critique"] = self._read_json_required(
                    critiques_dir / f"{node_id}.json"
                )
            node = Node.from_dict(payload)
            if node.node_id != node_id:
                raise ArgusValidationError(
                    f"Node file {node_id!r} contains mismatched node_id {node.node_id!r}."
                )
            nodes[node_id] = node

        learning_payload = self._read_json_required(run_dir / manifest.learning_notes_path)
        if not _is_sequence(learning_payload):
            raise ArgusValidationError(
                f"learning_notes must be a list, got {type(learning_payload).__name__}."
            )
        learning_notes = [LearningNote.from_dict(item) for item in learning_payload]

        return SearchState(
            problem_spec=problem_spec,
            root_id=index.root_id,
            nodes=nodes,
            archive_ids=index.archive_ids,
            frontier_ids=index.frontier_ids,
            pruned_ids=index.pruned_ids,
            winner_ids=index.winner_ids,
            islands=index.islands,
            learning_notes=learning_notes,
            budget_spent=index.budget_spent,
            step_count=index.step_count,
        )

    def _sync_nodes(
        self,
        run_dir: Path,
        manifest: RunManifest,
        nodes: Mapping[str, Node],
    ) -> None:
        nodes_dir = run_dir / manifest.nodes_dir
        scores_dir = run_dir / manifest.scores_dir
        critiques_dir = run_dir / manifest.critiques_dir

        desired_node_ids = {
            _normalize_path_segment(node_id, "node_id"): node
            for node_id, node in nodes.items()
        }
        for node_id, node in desired_node_ids.items():
            if node.node_id != node_id:
                raise ArgusValidationError(
                    f"nodes key {node_id!r} does not match embedded node_id {node.node_id!r}."
                )

        self._remove_stale_json_files(nodes_dir, set(desired_node_ids))
        self._remove_stale_json_files(
            scores_dir,
            {node_id for node_id, node in desired_node_ids.items() if node.score is not None},
        )
        self._remove_stale_json_files(
            critiques_dir,
            {node_id for node_id, node in desired_node_ids.items() if node.critique is not None},
        )

        for node_id in sorted(desired_node_ids):
            node = desired_node_ids[node_id]
            node_payload = node.to_dict()
            node_payload.pop("score", None)
            node_payload.pop("critique", None)
            self._write_json(nodes_dir / f"{node_id}.json", node_payload)

            score_path = scores_dir / f"{node_id}.json"
            critique_path = critiques_dir / f"{node_id}.json"
            if node.score is not None:
                self._write_json(score_path, node.score.to_dict())
            elif score_path.exists():
                score_path.unlink()

            if node.critique is not None:
                self._write_json(critique_path, node.critique.to_dict())
            elif critique_path.exists():
                critique_path.unlink()

    def _ensure_run_layout(self, run_dir: Path, manifest: RunManifest) -> None:
        for relative_path in (manifest.nodes_dir, manifest.scores_dir, manifest.critiques_dir):
            (run_dir / relative_path).mkdir(parents=True, exist_ok=True)

    def _remove_stale_json_files(self, directory: Path, keep_ids: set[str]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.glob("*.json"):
            if path.stem not in keep_ids:
                path.unlink()

    def _write_manifest(self, run_dir: Path, manifest: RunManifest) -> None:
        self._write_json(run_dir / "run.json", manifest.to_dict())

    def _write_optional_json(
        self,
        run_dir: Path,
        relative_path: str,
        payload: object | None,
    ) -> str | None:
        path = run_dir / relative_path
        if payload is None:
            if path.exists():
                path.unlink()
            return None

        self._write_json(path, payload)
        return relative_path

    def _write_optional_text(
        self,
        run_dir: Path,
        relative_path: str,
        text: str | None,
    ) -> str | None:
        path = run_dir / relative_path
        if text is None:
            if path.exists():
                path.unlink()
            return None

        normalized_text = _normalize_non_empty_string(text, "summary_markdown")
        path.write_text(normalized_text, encoding="utf-8")
        return relative_path

    def _write_research_markdown(
        self,
        run_dir: Path,
        relative_dir: str,
        markdown_files: Mapping[str, str] | None,
    ) -> str | None:
        root = run_dir / relative_dir
        if not markdown_files:
            if root.exists():
                shutil.rmtree(root)
            return None

        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        for relative_path, text in sorted(markdown_files.items()):
            normalized_relative_path = _normalize_relative_path(relative_path, "research_markdown path")
            normalized_text = _normalize_non_empty_string(text, "research_markdown")
            target_path = root / normalized_relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(normalized_text, encoding="utf-8")
        return relative_dir

    def _validate_final_recommendation(
        self,
        recommendation: FinalRecommendation,
        state: SearchState,
    ) -> None:
        if not isinstance(recommendation, FinalRecommendation):
            raise ArgusValidationError(
                "final_recommendation must be a FinalRecommendation instance, "
                f"got {type(recommendation).__name__}."
            )

        node_ids = set(state.nodes)
        referenced_ids = {recommendation.best_bet_node_id}
        if recommendation.conservative_node_id is not None:
            referenced_ids.add(recommendation.conservative_node_id)
        if recommendation.high_upside_node_id is not None:
            referenced_ids.add(recommendation.high_upside_node_id)
        referenced_ids.update(recommendation.rejected_but_insightful_ids)
        for decision in recommendation.pairwise_decisions:
            referenced_ids.add(decision.left_node_id)
            referenced_ids.add(decision.right_node_id)
            referenced_ids.add(decision.winner_node_id)

        unknown_ids = sorted(referenced_ids - node_ids)
        if unknown_ids:
            raise ArgusValidationError(
                "final recommendation references unknown node ids: "
                + ", ".join(unknown_ids)
            )

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_json_required(self, path: Path) -> object:
        if not path.is_file():
            raise ArgusValidationError(f"Missing required JSON file: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ArgusValidationError(f"Invalid JSON in {path}: {exc}") from exc


def _json_file_stems(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {path.stem for path in directory.glob("*.json") if path.is_file()}


def _validate_payload_keys(
    payload: object,
    *,
    field_name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise ArgusValidationError(
            f"{field_name} must be a mapping, got {type(payload).__name__}."
        )
    optional_keys = optional or set()
    allowed = required | optional_keys
    keys = set(payload)
    missing = sorted(required - keys)
    if missing:
        raise ArgusValidationError(
            f"{field_name} is missing required keys: {', '.join(missing)}."
        )
    extra = sorted(keys - allowed)
    if extra:
        raise ArgusValidationError(
            f"{field_name} contains unknown keys: {', '.join(extra)}."
        )
    return payload


def _normalize_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ArgusValidationError(
            f"{field_name} must be a mapping, got {type(value).__name__}."
        )
    for key in value:
        if not isinstance(key, str):
            raise ArgusValidationError(
                f"{field_name} must use string keys, got {type(key).__name__}."
            )
    return value


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


def _normalize_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgusValidationError(
            f"{field_name} must be an integer, got {type(value).__name__}."
        )
    if value <= 0:
        raise ArgusValidationError(f"{field_name} must be greater than 0.")
    return value


def _normalize_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArgusValidationError(
            f"{field_name} must be an integer, got {type(value).__name__}."
        )
    if value < 0:
        raise ArgusValidationError(f"{field_name} must not be negative.")
    return value


def _normalize_enum(value: object, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as exc:
            allowed = ", ".join(member.value for member in enum_type)
            raise ArgusValidationError(
                f"{field_name} must be one of: {allowed}."
            ) from exc
    raise ArgusValidationError(
        f"{field_name} must be a string or {enum_type.__name__}, got {type(value).__name__}."
    )


def _normalize_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        normalized = value
    elif isinstance(value, str):
        try:
            normalized = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ArgusValidationError(
                f"{field_name} must be an ISO-8601 datetime string."
            ) from exc
    else:
        raise ArgusValidationError(
            f"{field_name} must be a datetime or string, got {type(value).__name__}."
        )

    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc)


def _dump_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_relative_path(value: object, field_name: str) -> str:
    normalized = _normalize_non_empty_string(value, field_name)
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ArgusValidationError(
            f"{field_name} must be a relative path inside the run directory."
        )
    return path.as_posix()


def _normalize_optional_relative_path(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_relative_path(value, field_name)


def _normalize_path_segment(value: object, field_name: str) -> str:
    normalized = _normalize_non_empty_string(value, field_name)
    if normalized in {".", ".."} or Path(normalized).name != normalized:
        raise ArgusValidationError(
            f"{field_name} must be a single path segment, got {normalized!r}."
        )
    return normalized


def _normalize_unique_string_list(values: object, field_name: str) -> list[str]:
    if not _is_sequence(values):
        raise ArgusValidationError(
            f"{field_name} must be a list of strings, got {type(values).__name__}."
        )
    normalized = [_normalize_non_empty_string(value, f"{field_name}[{index}]") for index, value in enumerate(values)]
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    if duplicates:
        raise ArgusValidationError(
            f"{field_name} contains duplicate values: {', '.join(duplicates)}."
        )
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


def _normalize_json_object(value: object, field_name: str) -> dict[str, JSONValue]:
    if not isinstance(value, Mapping):
        raise ArgusValidationError(
            f"{field_name} must be a mapping, got {type(value).__name__}."
        )
    normalized: dict[str, JSONValue] = {}
    for key in sorted(value):
        if not isinstance(key, str):
            raise ArgusValidationError(
                f"{field_name} keys must be strings, got {type(key).__name__}."
            )
        normalized[key] = _normalize_json_value(value[key], f"{field_name}[{key!r}]")
    return normalized


def _normalize_json_value(value: object, field_name: str) -> JSONValue:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArgusValidationError(
                f"{field_name} must be JSON-serializable and finite."
            )
        return value
    if isinstance(value, Mapping):
        return _normalize_json_object(value, field_name)
    if _is_sequence(value):
        return [_normalize_json_value(item, f"{field_name}[]") for item in value]
    raise ArgusValidationError(
        f"{field_name} must be JSON-serializable, got {type(value).__name__}."
    )


def _normalize_learning_notes(value: object, field_name: str) -> list[LearningNote]:
    if not _is_sequence(value):
        raise ArgusValidationError(
            f"{field_name} must be a list of learning notes, got {type(value).__name__}."
        )
    normalized: list[LearningNote] = []
    for index, note in enumerate(value):
        if not isinstance(note, LearningNote):
            raise ArgusValidationError(
                f"{field_name}[{index}] must be a LearningNote instance, "
                f"got {type(note).__name__}."
            )
        normalized.append(note)
    return normalized


def _feedback_routing_summary(
    *,
    node: Node,
    feedback: OutcomeFeedback,
) -> ProviderRoutingStats:
    reward = _feedback_reward(feedback)
    routing_keys = _node_feedback_routing_keys(node)
    if reward == 0.0 or not routing_keys:
        return ProviderRoutingStats.empty()

    per_key_reward = reward / len(routing_keys)
    return ProviderRoutingStats(
        entries=[
            ProviderRoutingStatsEntry(
                provider_name=provider_name,
                action_name=action_name,
                invocation_count=1,
                total_reward=per_key_reward,
                last_run_id=feedback.run_id,
                last_updated_at=feedback.recorded_at,
            )
            for provider_name, action_name in sorted(routing_keys)
        ],
        updated_at=feedback.recorded_at,
    )


def _node_feedback_routing_keys(node: Node) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = {(node.provider_name, node.action_type.value)}
    provider_routing = node.metadata.get("provider_routing")
    if not isinstance(provider_routing, Mapping):
        return keys
    for raw_action_name, raw_provider_names in provider_routing.items():
        if not isinstance(raw_action_name, str) or not _is_sequence(raw_provider_names):
            continue
        action_name = raw_action_name.strip()
        if not action_name:
            continue
        for raw_provider_name in raw_provider_names:
            if not isinstance(raw_provider_name, str):
                continue
            provider_name = raw_provider_name.strip()
            if provider_name:
                keys.add((provider_name, action_name))
    return keys


def _feedback_reward(feedback: OutcomeFeedback) -> float:
    outcome = feedback.outcome_status.value
    if outcome == "validated":
        return 3.0
    if outcome == "mixed":
        return 1.0
    if outcome == "invalidated":
        return -3.0
    return 0.0


def _copy_json_object(value: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    return json.loads(json.dumps(value, sort_keys=True))


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
