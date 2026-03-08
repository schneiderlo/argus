from __future__ import annotations

import json
import os
import re
from typing import Any

from argus.providers.base import ProviderArtifacts, StructuredOutputSchema
from argus.providers.cli_base import CliProviderBase, _ResponseExtractionError

_MARKDOWN_FENCE_PATTERN = re.compile(
    r"^\s*```(?:[A-Za-z0-9_+-]+)?\s*([\s\S]*?)\s*```\s*$",
    re.IGNORECASE,
)


class GeminiProvider(CliProviderBase):
    name = "gemini"
    prompt_worker_name = "Gemini"
    default_binary = "gemini"
    command_display_name = "gemini"
    model_env_var = "GEMINI_MODEL"
    invalid_json_retries = 1

    def _build_command(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
        output_schema: StructuredOutputSchema[Any],
    ) -> list[str]:
        command = [
            self.binary,
            "--prompt",
            prompt_text,
            "--output-format",
            "json",
        ]
        if self.model is not None:
            command.extend(["--model", self.model])
        return command

    def _build_runner_kwargs(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
    ) -> dict[str, object]:
        env = dict(os.environ)
        env.setdefault("NO_COLOR", "1")
        env.setdefault("NO_BROWSER", "1")
        return {
            "cwd": artifacts.sandbox_dir,
            "env": env,
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
                message="gemini completed without writing a JSON response envelope.",
            )

        try:
            envelope = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise _ResponseExtractionError(
                error_type="invalid_json",
                message=f"gemini returned invalid JSON output: {exc}",
            ) from exc

        if not isinstance(envelope, dict):
            raise _ResponseExtractionError(
                error_type="invalid_json",
                message="gemini returned a non-object JSON response envelope.",
            )

        response = envelope.get("response")
        if not isinstance(response, str):
            raise _ResponseExtractionError(
                error_type="missing_output",
                message="gemini JSON output did not include a string `response` field.",
            )
        return _unwrap_markdown_fence(response)


def _unwrap_markdown_fence(text: str) -> str:
    match = _MARKDOWN_FENCE_PATTERN.match(text)
    if match is None:
        return text.strip()
    return match.group(1).strip()
