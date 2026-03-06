from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from argus.errors import ArgusValidationError
from argus.providers.base import ProviderArtifacts, StructuredOutputSchema
from argus.providers.cli_base import CliProviderBase, _ResponseExtractionError


class CodexProvider(CliProviderBase):
    name = "codex"
    prompt_worker_name = "Codex"
    default_binary = "codex"
    command_display_name = "codex exec"
    model_env_var = "CODEX_MODEL"

    def __init__(
        self,
        *,
        artifacts_root: Path,
        binary: str = "codex",
        model: str | None = None,
        timeout_seconds: float = 300.0,
        runner: Any = subprocess.run,
        sandbox_mode: str = "read-only",
    ) -> None:
        if not isinstance(sandbox_mode, str) or not sandbox_mode.strip():
            raise ArgusValidationError("sandbox_mode must be a non-empty string.")

        super().__init__(
            artifacts_root=artifacts_root,
            binary=binary,
            model=model,
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        self.sandbox_mode = sandbox_mode.strip()

    def _build_command(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
        output_schema: StructuredOutputSchema[Any],
    ) -> list[str]:
        command = [
            self.binary,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            self.sandbox_mode,
            "--color",
            "never",
            "--json",
            "-C",
            str(artifacts.sandbox_dir),
            "--output-schema",
            str(artifacts.schema_path),
            "-o",
            str(artifacts.last_message_path),
            "-",
        ]
        if self.model is not None:
            command[2:2] = ["--model", self.model]
        return command

    def _build_runner_kwargs(
        self,
        artifacts: ProviderArtifacts,
        prompt_text: str,
    ) -> dict[str, object]:
        return {"input": prompt_text}

    def _extract_response_text(
        self,
        *,
        artifacts: ProviderArtifacts,
        stdout_text: str,
        stderr_text: str,
    ) -> str:
        if not artifacts.last_message_path.is_file():
            raise _ResponseExtractionError(
                error_type="missing_output",
                message="codex exec completed without writing the final message artifact.",
            )
        return artifacts.last_message_path.read_text(encoding="utf-8")
