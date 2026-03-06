from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

from argus.config import ArgusConfig
from argus.errors import ArgusUserError
from argus.storage import FileSystemStateStore, PersistedRun, RunManifest, RunStatus

_RECOGNIZED_AGENT_RUN_FILES = {
    "codex-events.jsonl",
    "codex-output.txt",
    "last-message.md",
    "metadata.env",
    "previous-verify.txt",
    "prompt.md",
    "verify.txt",
}

_RECOGNIZED_ARGUS_RUN_FILES = {
    "final-recommendation.json",
    "learning-notes.json",
    "learning-memory.json",
    "outcome-feedback-ledger.json",
    "outcome-feedback.json",
    "provider-routing-stats.json",
    "problem-spec.json",
    "reusable-learning-context.json",
    "routing-summary.json",
    "run.json",
    "state.json",
    "summary.md",
}


@dataclass(frozen=True, slots=True)
class InspectionSummary:
    """Serializable description of an artifact target."""

    target: str
    kind: str
    file_count: int
    files: list[str]
    metadata: dict[str, str]
    recognized_artifacts: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProviderInvocationSummary:
    invocation_id: str
    action_name: str
    state: str
    started_at: str
    pid: int | None = None
    elapsed: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunStatusSummary:
    run_id: str
    status: str
    provider_name: str
    created_at: str
    updated_at: str
    request: str
    budget: int
    budget_spent: int
    step_count: int
    node_count: int
    archive_count: int
    frontier_count: int
    pruned_count: int
    winner_count: int
    current_action: str | None
    active_provider_invocation_count: int
    active_provider_invocations: list[ProviderInvocationSummary]
    recent_provider_invocations: list[ProviderInvocationSummary]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "provider_name": self.provider_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "request": self.request,
            "budget": self.budget,
            "budget_spent": self.budget_spent,
            "step_count": self.step_count,
            "node_count": self.node_count,
            "archive_count": self.archive_count,
            "frontier_count": self.frontier_count,
            "pruned_count": self.pruned_count,
            "winner_count": self.winner_count,
            "current_action": self.current_action,
            "active_provider_invocation_count": self.active_provider_invocation_count,
            "active_provider_invocations": [
                invocation.to_dict() for invocation in self.active_provider_invocations
            ],
            "recent_provider_invocations": [
                invocation.to_dict() for invocation in self.recent_provider_invocations
            ],
        }


def resolve_inspection_target(
    config: ArgusConfig,
    path: Path | None,
    *,
    latest_agent_run: bool,
) -> Path:
    if path is not None:
        return path.expanduser().resolve()

    if latest_agent_run:
        pointer = config.latest_agent_run_pointer
        if pointer.is_file():
            target_text = pointer.read_text(encoding="utf-8").strip()
            if not target_text:
                raise ArgusUserError(
                    f"Latest agent run pointer is empty: {pointer}"
                )
            return Path(target_text).expanduser().resolve()

        latest_run = _latest_directory(config.agent_runs_dir)
        if latest_run is not None:
            return latest_run

        raise ArgusUserError(
            "No agent-run artifacts found. Expected artifacts/latest-run.txt or a "
            "directory under artifacts/agent_runs/."
        )

    raise ArgusUserError("Provide a target path or pass --latest-agent-run.")


def inspect_artifact_path(target: Path) -> InspectionSummary:
    if not target.exists():
        raise ArgusUserError(f"Artifact path does not exist: {target}")

    if target.is_file():
        return InspectionSummary(
            target=str(target),
            kind="file",
            file_count=1,
            files=[target.name],
            metadata={},
            recognized_artifacts=[],
        )

    files = sorted(
        str(path.relative_to(target))
        for path in target.rglob("*")
        if path.is_file()
    )
    kind = "directory"
    metadata = _parse_metadata_file(target / "metadata.env")
    run_manifest = _parse_run_manifest_file(target / "run.json")
    if run_manifest is not None:
        kind = "argus_run"
        metadata = {
            "budget": str(run_manifest.budget),
            "created_at": run_manifest.created_at.isoformat().replace("+00:00", "Z"),
            "provider_name": run_manifest.provider_name,
            "run_id": run_manifest.run_id,
            "status": run_manifest.status.value,
            "updated_at": run_manifest.updated_at.isoformat().replace("+00:00", "Z"),
        }
    elif any(Path(entry).name in _RECOGNIZED_AGENT_RUN_FILES for entry in files):
        kind = "agent_run"

    recognized_artifacts = sorted(
        entry
        for entry in files
        if Path(entry).name in _RECOGNIZED_AGENT_RUN_FILES
        or Path(entry).name in _RECOGNIZED_ARGUS_RUN_FILES
    )
    return InspectionSummary(
        target=str(target),
        kind=kind,
        file_count=len(files),
        files=files,
        metadata=metadata,
        recognized_artifacts=recognized_artifacts,
    )


def build_run_status_summary(
    config: ArgusConfig,
    *,
    run_id: str | None = None,
) -> RunStatusSummary:
    store = FileSystemStateStore(config.runs_dir)
    persisted_run = _resolve_status_run(store, run_id=run_id)
    manifest = persisted_run.manifest
    state = persisted_run.state
    active_processes = _active_provider_processes(config.provider_invocations_dir)
    recent_invocations = _recent_provider_invocations(
        config.provider_invocations_dir,
        run=persisted_run,
        active_processes=active_processes,
        limit=8,
    )
    active_invocations = [
        invocation for invocation in recent_invocations if invocation.state == "running"
    ]
    metadata = manifest.metadata
    current_action = None
    if active_invocations:
        action_names = list(dict.fromkeys(item.action_name for item in active_invocations))
        current_action = ", ".join(action_names)
    elif isinstance(metadata.get("failed_action"), str):
        current_action = str(metadata["failed_action"])

    budget_spent = 0 if state is None else state.budget_spent
    step_count = 0 if state is None else state.step_count
    node_count = 0 if state is None else len(state.nodes)
    archive_count = 0 if state is None else len(state.archive_ids)
    frontier_count = 0 if state is None else len(state.frontier_ids)
    pruned_count = 0 if state is None else len(state.pruned_ids)
    winner_count = 0 if state is None else len(state.winner_ids)
    return RunStatusSummary(
        run_id=manifest.run_id,
        status=manifest.status.value,
        provider_name=manifest.provider_name,
        created_at=_format_datetime(manifest.created_at),
        updated_at=_format_datetime(manifest.updated_at),
        request=persisted_run.problem_spec.request,
        budget=manifest.budget,
        budget_spent=budget_spent,
        step_count=step_count,
        node_count=node_count,
        archive_count=archive_count,
        frontier_count=frontier_count,
        pruned_count=pruned_count,
        winner_count=winner_count,
        current_action=current_action,
        active_provider_invocation_count=len(active_invocations),
        active_provider_invocations=active_invocations,
        recent_provider_invocations=recent_invocations,
    )


def render_inspection_report(summary: InspectionSummary) -> str:
    lines = [
        f"target={summary.target}",
        f"kind={summary.kind}",
        f"file_count={summary.file_count}",
    ]

    if summary.metadata:
        lines.append("metadata:")
        for key in sorted(summary.metadata):
            lines.append(f"  {key}={summary.metadata[key]}")

    if summary.recognized_artifacts:
        lines.append("recognized_artifacts:")
        for artifact in summary.recognized_artifacts:
            lines.append(f"  {artifact}")

    if summary.files:
        lines.append("files:")
        for path in summary.files:
            lines.append(f"  {path}")

    return "\n".join(lines)


def render_run_status_report(summary: RunStatusSummary, *, color: bool = False) -> str:
    title = "Argus Run Status"
    if color:
        title = _style(title, "bold", color=color)
    status_text = summary.status
    current_action_text = summary.current_action
    if color:
        status_text = _style(
            summary.status,
            _status_color(summary.status),
            color=color,
        )
        if summary.current_action is not None:
            current_action_text = _style(summary.current_action, "cyan", color=color)

    lines = [
        title,
        f"run_id={summary.run_id}",
        f"status={status_text}",
        f"provider={summary.provider_name}",
        f"created_at={summary.created_at}",
        f"updated_at={summary.updated_at}",
        "",
        "request:",
        f"  {summary.request}",
        "",
        "progress:",
        f"  budget={summary.budget_spent}/{summary.budget}",
        f"  steps={summary.step_count}",
        f"  nodes={summary.node_count}",
        f"  archive={summary.archive_count}",
        f"  frontier={summary.frontier_count}",
        f"  pruned={summary.pruned_count}",
        f"  winners={summary.winner_count}",
    ]
    if current_action_text is not None:
        lines.extend(["", f"current_action={current_action_text}"])
    lines.append(
        f"active_provider_invocations={summary.active_provider_invocation_count}"
    )
    if summary.active_provider_invocations:
        lines.append("")
        lines.append("active_invocations:")
        for invocation in summary.active_provider_invocations:
            pid_text = "" if invocation.pid is None else f" pid={invocation.pid}"
            elapsed_text = (
                "" if invocation.elapsed is None else f" elapsed={invocation.elapsed}"
            )
            state_text = invocation.state
            if color:
                state_text = _style(
                    invocation.state,
                    _status_color(invocation.state),
                    color=color,
                )
            lines.append(
                f"  - {invocation.action_name}  state={state_text}{pid_text}{elapsed_text}"
            )
    if summary.recent_provider_invocations:
        lines.append("")
        lines.append("recent_invocations:")
        for invocation in summary.recent_provider_invocations:
            pid_text = "" if invocation.pid is None else f" pid={invocation.pid}"
            elapsed_text = (
                "" if invocation.elapsed is None else f" elapsed={invocation.elapsed}"
            )
            state_text = invocation.state
            if color:
                state_text = _style(
                    invocation.state,
                    _status_color(invocation.state),
                    color=color,
                )
            lines.append(
                f"  - {invocation.started_at}  {invocation.action_name}  state={state_text}{pid_text}{elapsed_text}"
            )
    return "\n".join(lines)


def _latest_directory(root: Path) -> Path | None:
    if not root.is_dir():
        return None

    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def _resolve_status_run(
    store: FileSystemStateStore,
    *,
    run_id: str | None,
) -> PersistedRun:
    if run_id is not None:
        return store.load_run(run_id)
    manifests = store.list_runs()
    if not manifests:
        raise ArgusUserError("No Argus runs found under artifacts/runs/.")
    running = [manifest for manifest in manifests if manifest.status is RunStatus.RUNNING]
    candidates = running or manifests
    selected = max(
        candidates,
        key=lambda manifest: (manifest.updated_at, manifest.created_at, manifest.run_id),
    )
    return store.load_run(selected.run_id)


def _active_provider_processes(
    invocations_root: Path,
) -> dict[str, ProviderInvocationSummary]:
    if not invocations_root.exists():
        return {}
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid,etime,command"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return {}
    if completed.returncode != 0:
        return {}

    pattern = re.compile(
        re.escape(str(invocations_root)) + r"/([^/\s]+)/workspace"
    )
    active: dict[str, ProviderInvocationSummary] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+)\s+(\S+)\s+(.+)$", line)
        if match is None:
            continue
        pid_text, elapsed, command = match.groups()
        path_match = pattern.search(command)
        if path_match is None:
            continue
        invocation_id = path_match.group(1)
        started_at = _format_datetime(_parse_invocation_started_at(invocation_id))
        action_name = _invocation_action_name(invocation_id)
        active[invocation_id] = ProviderInvocationSummary(
            invocation_id=invocation_id,
            action_name=action_name,
            state="running",
            started_at=started_at,
            pid=int(pid_text),
            elapsed=elapsed,
        )
    return active


def _recent_provider_invocations(
    invocations_root: Path,
    *,
    run: PersistedRun,
    active_processes: dict[str, ProviderInvocationSummary],
    limit: int,
) -> list[ProviderInvocationSummary]:
    if not invocations_root.is_dir():
        return []
    not_before = run.manifest.created_at - timedelta(seconds=1)
    not_after = None if run.manifest.status is RunStatus.RUNNING else run.manifest.updated_at + timedelta(seconds=2)
    collected: list[tuple[datetime, ProviderInvocationSummary]] = []
    for invocation_dir in invocations_root.iterdir():
        if not invocation_dir.is_dir():
            continue
        invocation_id = invocation_dir.name
        started_at = _parse_invocation_started_at(invocation_id)
        if started_at is None or started_at < not_before:
            continue
        if not_after is not None and started_at > not_after:
            continue
        if invocation_id in active_processes:
            collected.append((started_at, active_processes[invocation_id]))
            continue
        metadata_path = invocation_dir / "metadata.json"
        state = "running"
        action_name = _invocation_action_name(invocation_id)
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metadata = {}
            raw_state = metadata.get("status")
            if isinstance(raw_state, str) and raw_state.strip():
                state = raw_state.strip()
            raw_action_name = metadata.get("action_name")
            if isinstance(raw_action_name, str) and raw_action_name.strip():
                action_name = raw_action_name.strip()
        elif (invocation_dir / "failure.json").is_file():
            state = "failed"
        collected.append(
            (
                started_at,
                ProviderInvocationSummary(
                    invocation_id=invocation_id,
                    action_name=action_name,
                    state=state,
                    started_at=_format_datetime(started_at),
                ),
            )
        )
    return [
        summary
        for _, summary in sorted(collected, key=lambda item: item[0], reverse=True)[:limit]
    ]


def _parse_invocation_started_at(invocation_id: str) -> datetime | None:
    match = re.match(r"^(\d{8}T\d{6}\d{6}Z)-", invocation_id)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _invocation_action_name(invocation_id: str) -> str:
    match = re.match(r"^\d{8}T\d{6}\d{6}Z-(.+)$", invocation_id)
    if match is None:
        return invocation_id
    return match.group(1).replace("-", "_")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_color(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"completed", "ok"}:
        return "green"
    if normalized in {"running"}:
        return "yellow"
    if normalized in {"failed"}:
        return "red"
    return "cyan"


def _style(text: str, token: str, *, color: bool) -> str:
    if not color:
        return text
    codes = {
        "bold": "1",
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "cyan": "36",
    }
    code = codes.get(token)
    if code is None:
        return text
    return f"\033[{code}m{text}\033[0m"


def _parse_metadata_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    metadata: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        metadata[key] = value
    return metadata


def _parse_run_manifest_file(path: Path) -> RunManifest | None:
    if not path.is_file():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArgusUserError(f"Invalid run metadata JSON at {path}: {exc}") from exc

    return RunManifest.from_dict(payload)
