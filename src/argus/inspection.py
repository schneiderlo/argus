from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from argus.config import ArgusConfig
from argus.errors import ArgusUserError

_RECOGNIZED_AGENT_RUN_FILES = {
    "codex-events.jsonl",
    "codex-output.txt",
    "last-message.md",
    "metadata.env",
    "previous-verify.txt",
    "prompt.md",
    "verify.txt",
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
    metadata = _parse_metadata_file(target / "metadata.env")
    recognized_artifacts = sorted(
        entry for entry in files if Path(entry).name in _RECOGNIZED_AGENT_RUN_FILES
    )
    return InspectionSummary(
        target=str(target),
        kind="directory",
        file_count=len(files),
        files=files,
        metadata=metadata,
        recognized_artifacts=recognized_artifacts,
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


def _latest_directory(root: Path) -> Path | None:
    if not root.is_dir():
        return None

    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


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
