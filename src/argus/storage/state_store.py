from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path

from argus.errors import ArgusUserError, ArgusValidationError
from argus.models import (
    FinalRecommendation,
    JSONValue,
    LearningNote,
    Node,
    ProblemSpec,
    ProviderRoutingStats,
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
    final_recommendation_path: str | None = None
    summary_path: str | None = None
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
            "final_recommendation_path": self.final_recommendation_path,
            "summary_path": self.summary_path,
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
            final_recommendation_path=data["final_recommendation_path"],
            summary_path=data["summary_path"],
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
        )
        return cls(
            root_id=data["root_id"],
            node_ids=data["node_ids"],
            archive_ids=data["archive_ids"],
            frontier_ids=data["frontier_ids"],
            pruned_ids=data["pruned_ids"],
            winner_ids=data["winner_ids"],
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
            budget_spent=state.budget_spent,
            step_count=state.step_count,
        )


@dataclass(frozen=True, slots=True)
class PersistedRun:
    path: Path
    manifest: RunManifest
    problem_spec: ProblemSpec
    state: SearchState | None = None
    final_recommendation: FinalRecommendation | None = None
    summary_markdown: str | None = None
    routing_summary: ProviderRoutingStats | None = None


class FileSystemStateStore:
    _ROUTING_SUMMARY_PATH = "routing-summary.json"
    _ROUTING_STATS_PATH = "provider-routing-stats.json"

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.expanduser().resolve()

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

        refreshed_manifest = replace(
            manifest,
            status=normalized_status,
            updated_at=_normalize_datetime(updated_at or datetime.now(timezone.utc), "updated_at"),
            state_path=state_path,
            learning_notes_path=learning_notes_path,
            final_recommendation_path=final_recommendation_path,
            summary_path=summary_path,
            metadata=merged_metadata,
            error=normalized_error,
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
            final_recommendation=final_recommendation,
            summary_markdown=summary_markdown,
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

        refreshed_manifest = replace(
            manifest,
            status=normalized_status,
            updated_at=_normalize_datetime(updated_at or datetime.now(timezone.utc), "updated_at"),
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
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return _normalize_json_object(value, field_name)
    if _is_sequence(value):
        return [_normalize_json_value(item, f"{field_name}[]") for item in value]
    raise ArgusValidationError(
        f"{field_name} must be JSON-serializable, got {type(value).__name__}."
    )


def _copy_json_object(value: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    return json.loads(json.dumps(value, sort_keys=True))


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
