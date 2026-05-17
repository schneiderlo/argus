from __future__ import annotations

from abc import ABC, abstractmethod
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
from argus.providers.prompting import render_provider_prompt

_SCHEMA_META_KEYS = frozenset(
    {
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "contains",
        "default",
        "description",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
    }
)


class CliProviderBase(ABC):
    name: str
    prompt_worker_name: str
    default_binary: str
    command_display_name: str
    model_env_var: str | None = None
    invalid_json_retries: int = 0

    def __init__(
        self,
        *,
        artifacts_root: Path,
        binary: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        service_tier: str | None = None,
        web_search: bool = False,
        timeout_seconds: float = 300.0,
        runner: Any = subprocess.run,
    ) -> None:
        if timeout_seconds <= 0:
            raise ArgusValidationError("timeout_seconds must be greater than zero.")

        resolved_binary = (binary or self.default_binary).strip()
        if not resolved_binary:
            raise ArgusValidationError("binary must be a non-empty string.")
        if not isinstance(self.invalid_json_retries, int) or self.invalid_json_retries < 0:
            raise ArgusValidationError("invalid_json_retries must be a non-negative integer.")

        self.artifacts_root = artifacts_root.expanduser().resolve()
        self.binary = resolved_binary
        self.model = _resolve_model(model, env_var=self.model_env_var)
        self.reasoning_effort = _resolve_optional_string(
            reasoning_effort,
            field_name="reasoning_effort",
        )
        self.service_tier = _resolve_optional_string(
            service_tier,
            field_name="service_tier",
        )
        self.web_search = _resolve_bool(web_search, "web_search")
        self.timeout_seconds = timeout_seconds
        self.runner = runner

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
        prompt_text = self._render_prompt(
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

        command = self._build_command(
            artifacts=artifacts,
            prompt_text=prompt_text,
            output_schema=output_schema,
        )
        started_at = time.monotonic()
        runner_kwargs = {
            "text": True,
            "capture_output": True,
            "timeout": self.timeout_seconds,
            "check": False,
        }
        runner_kwargs.update(self._build_runner_kwargs(artifacts=artifacts, prompt_text=prompt_text))
        invalid_json_attempts_remaining = self.invalid_json_retries
        while True:
            try:
                completed = self.runner(command, **runner_kwargs)
            except subprocess.TimeoutExpired as exc:
                stderr_text = _coerce_subprocess_output(exc.stderr)
                stdout_text = _coerce_subprocess_output(exc.stdout)
                self._write_process_streams(artifacts, stdout_text, stderr_text)
                return self._raise_failure(
                    artifacts=artifacts,
                    action_name=normalized_action_name,
                    prompt_sha256=prompt_sha256,
                    message=(
                        f"{self.command_display_name} timed out after "
                        f"{self.timeout_seconds:.1f} seconds."
                    ),
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
                    action_name=normalized_action_name,
                    prompt_sha256=prompt_sha256,
                    message=f"Failed to execute {self.binary}: {exc}",
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
                    action_name=normalized_action_name,
                    prompt_sha256=prompt_sha256,
                    message=f"{self.command_display_name} exited with status {completed.returncode}.",
                    error_type="process_exit",
                    exit_status=completed.returncode,
                    stderr_excerpt=stderr_text,
                    timestamp=timestamp,
                    duration_ms=_duration_ms(started_at),
                )

            try:
                raw_message = self._extract_response_text(
                    artifacts=artifacts,
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                ).strip()
            except _ResponseExtractionError as exc:
                if exc.error_type == "invalid_json" and invalid_json_attempts_remaining > 0:
                    invalid_json_attempts_remaining -= 1
                    continue
                return self._raise_failure(
                    artifacts=artifacts,
                    action_name=normalized_action_name,
                    prompt_sha256=prompt_sha256,
                    message=exc.message,
                    error_type=exc.error_type,
                    exit_status=completed.returncode,
                    stderr_excerpt=stderr_text,
                    timestamp=timestamp,
                    duration_ms=_duration_ms(started_at),
                )

            if not raw_message:
                return self._raise_failure(
                    artifacts=artifacts,
                    action_name=normalized_action_name,
                    prompt_sha256=prompt_sha256,
                    message=f"{self.command_display_name} returned an empty final message.",
                    error_type="missing_output",
                    exit_status=completed.returncode,
                    stderr_excerpt=stderr_text,
                    timestamp=timestamp,
                    duration_ms=_duration_ms(started_at),
                )

            artifacts.last_message_path.write_text(raw_message, encoding="utf-8")

            try:
                raw_payload = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                if invalid_json_attempts_remaining > 0:
                    invalid_json_attempts_remaining -= 1
                    continue
                return self._raise_failure(
                    artifacts=artifacts,
                    action_name=normalized_action_name,
                    prompt_sha256=prompt_sha256,
                    message=f"{self.command_display_name} returned invalid JSON: {exc}",
                    error_type="invalid_json",
                    exit_status=completed.returncode,
                    stderr_excerpt=stderr_text,
                    timestamp=timestamp,
                    duration_ms=_duration_ms(started_at),
                )
            break

        artifacts.response_path.write_text(
            json.dumps(raw_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sanitized_payload, stripped_schema_keys = _strip_accidental_schema_metadata(
            raw_payload,
            output_schema.json_schema,
        )

        try:
            typed_payload = output_schema.validate(sanitized_payload)
        except Exception as exc:
            return self._raise_failure(
                artifacts=artifacts,
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
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
            web_search=self.web_search,
        )
        metadata = response.metadata_dict()
        metadata["duration_ms"] = _duration_ms(started_at)
        metadata["status"] = "ok"
        if stripped_schema_keys:
            metadata["stripped_schema_metadata_keys"] = stripped_schema_keys
        artifacts.metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if artifacts.failure_path.exists():
            artifacts.failure_path.unlink()
        return response

    def _prepare_artifacts(self, action_name: str, timestamp: datetime) -> ProviderArtifacts:
        invocation_id, invocation_dir = _allocate_invocation_dir(
            self.artifacts_root,
            action_name,
            timestamp,
        )
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

    def _render_prompt(
        self,
        *,
        action_name: str,
        problem_spec: ProblemSpec,
        input_payload: Mapping[str, JSONValue],
        output_schema: StructuredOutputSchema[Any],
    ) -> str:
        return render_provider_prompt(
            provider_name=self.prompt_worker_name,
            action_name=action_name,
            problem_spec=problem_spec,
            input_payload=input_payload,
            output_schema=output_schema,
            allow_web_search=self.web_search,
        )

    @abstractmethod
    def _build_command(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
        output_schema: StructuredOutputSchema[Any],
    ) -> list[str]:
        raise NotImplementedError

    def _build_runner_kwargs(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
    ) -> dict[str, object]:
        return {}

    @abstractmethod
    def _extract_response_text(
        self,
        *,
        artifacts: ProviderArtifacts,
        stdout_text: str,
        stderr_text: str,
    ) -> str:
        raise NotImplementedError

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
            provider_name=self.name,
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
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
            web_search=self.web_search,
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


class _ResponseExtractionError(Exception):
    def __init__(self, *, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def _allocate_invocation_dir(
    root: Path,
    action_name: str,
    timestamp: datetime,
) -> tuple[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    base = f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-{_slugify(action_name)}"
    suffix = 1
    while True:
        candidate = base if suffix == 1 else f"{base}-{suffix - 1:02d}"
        invocation_dir = root / candidate
        try:
            invocation_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            suffix += 1
            continue
        return candidate, invocation_dir


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


def _resolve_model(value: str | None, *, env_var: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if env_var is None:
        return None
    env_value = os.getenv(env_var)
    if isinstance(env_value, str) and env_value.strip():
        return env_value.strip()
    return None


def _resolve_optional_string(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ArgusValidationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _resolve_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ArgusValidationError(
            f"{field_name} must be a boolean, got {type(value).__name__}."
        )
    return value


def _strip_accidental_schema_metadata(
    payload: object,
    schema: Mapping[str, JSONValue],
) -> tuple[object, list[str]]:
    if not isinstance(payload, dict):
        return payload, []

    schema_type = schema.get("type")
    if schema_type != "object" and not (
        isinstance(schema_type, list) and "object" in schema_type
    ):
        return payload, []

    raw_properties = schema.get("properties")
    if not isinstance(raw_properties, Mapping):
        return payload, []

    allowed_properties = {str(key) for key in raw_properties}
    stripped_keys = sorted(
        str(key)
        for key in payload
        if str(key) not in allowed_properties and str(key) in _SCHEMA_META_KEYS
    )
    if not stripped_keys:
        return payload, []

    sanitized_payload = {
        key: value
        for key, value in payload.items()
        if str(key) not in stripped_keys
    }
    return sanitized_payload, stripped_keys


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
