from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArgusConfig:
    """Filesystem locations used by the CLI."""

    root_dir: Path
    artifacts_dir: Path
    runs_dir: Path
    agent_runs_dir: Path
    provider_invocations_dir: Path
    verify_dir: Path
    latest_agent_run_pointer: Path

    @classmethod
    def discover(cls, root: Path | None = None) -> "ArgusConfig":
        root_dir = (root or Path.cwd()).expanduser().resolve()
        artifacts_dir = root_dir / "artifacts"
        return cls(
            root_dir=root_dir,
            artifacts_dir=artifacts_dir,
            runs_dir=artifacts_dir / "runs",
            agent_runs_dir=artifacts_dir / "agent_runs",
            provider_invocations_dir=artifacts_dir / "provider_invocations",
            verify_dir=artifacts_dir / "verify",
            latest_agent_run_pointer=artifacts_dir / "latest-run.txt",
        )
