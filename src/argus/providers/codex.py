from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from argus.errors import ArgusValidationError
from argus.models import ActionType, JSONValue, ProblemSpec
from argus.providers.base import (
    ProviderArtifacts,
    ProviderFailure,
    ProviderInvocationError,
    ProviderResponse,
    StructuredOutputSchema,
)


class CodexProvider:
    name = "codex"

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
        if timeout_seconds <= 0:
            raise ArgusValidationError("timeout_seconds must be greater than zero.")
        if not isinstance(binary, str) or not binary.strip():
            raise ArgusValidationError("binary must be a non-empty string.")
        if not isinstance(sandbox_mode, str) or not sandbox_mode.strip():
            raise ArgusValidationError("sandbox_mode must be a non-empty string.")

        self.artifacts_root = artifacts_root.expanduser().resolve()
        self.binary = binary.strip()
        self.model = model.strip() if isinstance(model, str) and model.strip() else os.getenv(
            "CODEX_MODEL"
        )
        self.timeout_seconds = timeout_seconds
        self.runner = runner
        self.sandbox_mode = sandbox_mode.strip()

    def run_action(
        self,
        *,
        action_name: ActionType | str,
        problem_spec: ProblemSpec,
        input_payload: Mapping[str, JSONValue],
        output_schema: StructuredOutputSchema[Any],
    ) -> ProviderResponse[Any]:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        if not isinstance(input_payload, Mapping):
            raise ArgusValidationError(
                "input_payload must be a mapping, "
                f"got {type(input_payload).__name__}."
            )

        normalized_action_name = _normalize_action_name(action_name)
        normalized_input_payload = _normalize_json_mapping(input_payload, "input_payload")
        timestamp = datetime.now(timezone.utc)
        artifacts = self._prepare_artifacts(normalized_action_name, timestamp)
        prompt_text = _render_prompt(
            action_name=normalized_action_name,
            problem_spec=problem_spec,
            input_payload=normalized_input_payload,
            output_schema=output_schema,
        )
        prompt_sha256 = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

        artifacts.prompt_path.write_text(prompt_text, encoding="utf-8")
        artifacts.schema_path.write_text(
            json.dumps(output_schema.json_schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        command = self._build_command(artifacts)
        started_at = time.monotonic()

        try:
            completed = self.runner(
                command,
                input=prompt_text,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr_text = _coerce_subprocess_output(exc.stderr)
            stdout_text = _coerce_subprocess_output(exc.stdout)
            self._write_process_streams(artifacts, stdout_text, stderr_text)
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message=f"codex exec timed out after {self.timeout_seconds:.1f} seconds.",
                error_type="timeout",
                exit_status=None,
                stderr_excerpt=stderr_text,
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )
        except OSError as exc:
            self._write_process_streams(artifacts, "", str(exc))
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message=f"Failed to execute codex: {exc}",
                error_type="execution_error",
                exit_status=None,
                stderr_excerpt=str(exc),
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )

        stdout_text = completed.stdout or ""
        stderr_text = completed.stderr or ""
        self._write_process_streams(artifacts, stdout_text, stderr_text)

        if completed.returncode != 0:
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message=f"codex exec exited with status {completed.returncode}.",
                error_type="process_exit",
                exit_status=completed.returncode,
                stderr_excerpt=stderr_text,
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )

        if not artifacts.last_message_path.is_file():
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message="codex exec completed without writing the final message artifact.",
                error_type="missing_output",
                exit_status=completed.returncode,
                stderr_excerpt=stderr_text,
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )

        raw_message = artifacts.last_message_path.read_text(encoding="utf-8").strip()
        if not raw_message:
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message="codex exec wrote an empty final message.",
                error_type="missing_output",
                exit_status=completed.returncode,
                stderr_excerpt=stderr_text,
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )

        try:
            raw_payload = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message=f"codex exec returned invalid JSON: {exc}",
                error_type="invalid_json",
                exit_status=completed.returncode,
                stderr_excerpt=stderr_text,
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )

        artifacts.response_path.write_text(
            json.dumps(raw_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        try:
            typed_payload = output_schema.validate(raw_payload)
        except Exception as exc:
            return self._raise_failure(
                artifacts=artifacts,
                provider_name=self.name,
                action_name=normalized_action_name,
                prompt_sha256=prompt_sha256,
                message=f"Provider output failed schema validation: {exc}",
                error_type="schema_validation",
                exit_status=completed.returncode,
                stderr_excerpt=stderr_text,
                timestamp=timestamp,
                duration_ms=_duration_ms(started_at),
            )

        response = ProviderResponse(
            provider_name=self.name,
            action_name=normalized_action_name,
            payload=typed_payload,
            raw_payload=raw_payload,
            prompt_sha256=prompt_sha256,
            artifacts=artifacts,
            exit_status=completed.returncode,
            timestamp=timestamp,
            model=self.model,
        )
        metadata = response.metadata_dict()
        metadata["duration_ms"] = _duration_ms(started_at)
        metadata["status"] = "ok"
        artifacts.metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if artifacts.failure_path.exists():
            artifacts.failure_path.unlink()
        return response

    def _prepare_artifacts(self, action_name: str, timestamp: datetime) -> ProviderArtifacts:
        invocation_id = _allocate_invocation_id(self.artifacts_root, action_name, timestamp)
        invocation_dir = self.artifacts_root / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)
        sandbox_dir = invocation_dir / "workspace"
        sandbox_dir.mkdir()

        return ProviderArtifacts(
            invocation_id=invocation_id,
            invocation_dir=invocation_dir,
            prompt_path=invocation_dir / "prompt.md",
            schema_path=invocation_dir / "schema.json",
            last_message_path=invocation_dir / "last-message.json",
            response_path=invocation_dir / "response.json",
            stdout_path=invocation_dir / "stdout.jsonl",
            stderr_path=invocation_dir / "stderr.txt",
            metadata_path=invocation_dir / "metadata.json",
            sandbox_dir=sandbox_dir,
            failure_path=invocation_dir / "failure.json",
        )

    def _build_command(self, artifacts: ProviderArtifacts) -> list[str]:
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

    def _write_process_streams(
        self,
        artifacts: ProviderArtifacts,
        stdout_text: str,
        stderr_text: str,
    ) -> None:
        artifacts.stdout_path.write_text(stdout_text, encoding="utf-8")
        artifacts.stderr_path.write_text(stderr_text, encoding="utf-8")

    def _raise_failure(
        self,
        *,
        artifacts: ProviderArtifacts,
        provider_name: str,
        action_name: str,
        prompt_sha256: str,
        message: str,
        error_type: str,
        exit_status: int | None,
        stderr_excerpt: str | None,
        timestamp: datetime,
        duration_ms: int,
    ) -> ProviderResponse[Any]:
        failure = ProviderFailure(
            provider_name=provider_name,
            action_name=action_name,
            message=message,
            error_type=error_type,
            timestamp=timestamp,
            prompt_sha256=prompt_sha256,
            exit_status=exit_status,
            stderr_excerpt=_trim_excerpt(stderr_excerpt),
            prompt_path=artifacts.prompt_path,
            artifacts=artifacts,
            model=self.model,
        )
        artifacts.failure_path.write_text(
            json.dumps(failure.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metadata = failure.to_dict()
        metadata["duration_ms"] = duration_ms
        metadata["status"] = "failed"
        artifacts.metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise ProviderInvocationError(failure)


def _allocate_invocation_id(root: Path, action_name: str, timestamp: datetime) -> str:
    root.mkdir(parents=True, exist_ok=True)
    base = f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{_slugify(action_name)}"
    candidate = base
    suffix = 1
    while (root / candidate).exists():
        candidate = f"{base}-{suffix:02d}"
        suffix += 1
    return candidate


def _normalize_action_name(value: ActionType | str) -> str:
    if isinstance(value, ActionType):
        return value.value
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"action_name must be a string or ActionType, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError("action_name must not be empty.")
    return normalized


def _normalize_json_mapping(payload: Mapping[str, JSONValue], field_name: str) -> dict[str, JSONValue]:
    try:
        encoded = json.dumps(dict(payload), sort_keys=True)
    except TypeError as exc:
        raise ArgusValidationError(f"{field_name} must be JSON-serializable: {exc}") from exc
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ArgusValidationError(f"{field_name} must serialize to a JSON object.")
    return decoded


def _render_prompt(
    *,
    action_name: str,
    problem_spec: ProblemSpec,
    input_payload: Mapping[str, JSONValue],
    output_schema: StructuredOutputSchema[Any],
) -> str:
    sections = [
        "You are the Codex worker behind the Argus provider layer.",
        "Return exactly one JSON response that satisfies the supplied schema.",
        "Do not wrap the JSON in markdown fences.",
        "Do not run shell commands or write files.",
        "Treat the problem spec and input payload as the full source of truth.",
        "",
        f"Action: {action_name}",
        "",
        "Problem spec:",
        "```json",
        json.dumps(problem_spec.to_dict(), indent=2, sort_keys=True),
        "```",
        "",
        "Input payload:",
        "```json",
        json.dumps(dict(input_payload), indent=2, sort_keys=True),
        "```",
        "",
        f"Output schema name: {output_schema.name}",
        "Output schema:",
        "```json",
        json.dumps(output_schema.json_schema, indent=2, sort_keys=True),
        "```",
        "",
        "Return only the JSON value that matches the schema.",
    ]
    return "\n".join(sections).strip() + "\n"


def _slugify(value: str) -> str:
    chars = [character.lower() if character.isalnum() else "-" for character in value]
    collapsed = "".join(chars).strip("-")
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed or "action"


def _coerce_subprocess_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _trim_excerpt(value: str | None, *, limit: int = 4000) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _duration_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)
