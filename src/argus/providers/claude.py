from __future__ import annotations

import json
import os
from typing import Any

from argus.providers.base import ProviderArtifacts, StructuredOutputSchema
from argus.providers.cli_base import CliProviderBase, _ResponseExtractionError


class ClaudeProvider(CliProviderBase):
    name = "claude"
    prompt_worker_name = "Claude Code"
    default_binary = "claude"
    command_display_name = "claude -p"
    model_env_var = "CLAUDE_MODEL"

    def _build_command(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
        output_schema: StructuredOutputSchema[Any],
    ) -> list[str]:
        command = [
            self.binary,
            "-p",
            "--output-format",
            "json",
            "--input-format",
            "text",
            "--json-schema",
            json.dumps(output_schema.json_schema, sort_keys=True),
            "--tools",
            "",
            "--no-session-persistence",
            "--permission-mode",
            "default",
        ]
        if self.model is not None:
            command.extend(["--model", self.model])
        if self.reasoning_effort is not None:
            command.extend(["--effort", self.reasoning_effort])
        return command

    def _build_runner_kwargs(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
    ) -> dict[str, object]:
        env = dict(os.environ)
        env.setdefault("NO_COLOR", "1")
        return {
            "cwd": artifacts.sandbox_dir,
            "env": env,
            "input": prompt_text,
        }

    def _extract_response_text(
        self,
        *,
        artifacts: ProviderArtifacts,
        stdout_text: str,
        stderr_text: str,
    ) -> str:
        if not stdout_text.strip():
            raise _ResponseExtractionError(
                error_type="missing_output",
                message="claude completed without writing a JSON response envelope.",
            )

        try:
            envelope = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise _ResponseExtractionError(
                error_type="invalid_json",
                message=f"claude returned invalid JSON output: {exc}",
            ) from exc

        if not isinstance(envelope, dict):
            raise _ResponseExtractionError(
                error_type="invalid_json",
                message="claude returned a non-object JSON response envelope.",
            )

        structured_output = envelope.get("structured_output")
        if structured_output is None:
            subtype = envelope.get("subtype")
            message = "claude JSON output did not include `structured_output`."
            if isinstance(subtype, str) and subtype.strip():
                message = f"{message} Result subtype: {subtype.strip()}."
            raise _ResponseExtractionError(
                error_type="missing_output",
                message=message,
            )
        return json.dumps(structured_output, sort_keys=True)
