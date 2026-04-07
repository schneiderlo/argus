from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from argus.errors import ArgusError, ArgusValidationError
from argus.models import ActionType, JSONValue, ProblemSpec

T = TypeVar("T")


def _dump_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class StructuredOutputSchema(Generic[T]):
    name: str
    json_schema: dict[str, JSONValue]
    validator: Callable[[object], T]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ArgusValidationError("schema name must be a non-empty string.")
        if not isinstance(self.json_schema, Mapping):
            raise ArgusValidationError(
                "json_schema must be a mapping, "
                f"got {type(self.json_schema).__name__}."
            )
        if not callable(self.validator):
            raise ArgusValidationError("validator must be callable.")

        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "json_schema", dict(self.json_schema))

    def validate(self, payload: object) -> T:
        return self.validator(payload)


@dataclass(frozen=True, slots=True)
class ProviderArtifacts:
    invocation_id: str
    invocation_dir: Path
    prompt_path: Path
    schema_path: Path
    last_message_path: Path
    response_path: Path
    stdout_path: Path
    stderr_path: Path
    metadata_path: Path
    sandbox_dir: Path
    failure_path: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "invocation_id": self.invocation_id,
            "invocation_dir": str(self.invocation_dir),
            "prompt_path": str(self.prompt_path),
            "schema_path": str(self.schema_path),
            "last_message_path": str(self.last_message_path),
            "response_path": str(self.response_path),
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "metadata_path": str(self.metadata_path),
            "sandbox_dir": str(self.sandbox_dir),
            "failure_path": str(self.failure_path),
        }


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    provider_name: str
    action_name: str
    message: str
    error_type: str
    timestamp: datetime
    prompt_sha256: str
    exit_status: int | None
    stderr_excerpt: str | None
    prompt_path: Path
    artifacts: ProviderArtifacts
    model: str | None = None
    reasoning_effort: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider_name": self.provider_name,
            "action_name": self.action_name,
            "message": self.message,
            "error_type": self.error_type,
            "timestamp": _dump_timestamp(self.timestamp),
            "prompt_sha256": self.prompt_sha256,
            "exit_status": self.exit_status,
            "stderr_excerpt": self.stderr_excerpt,
            "prompt_path": str(self.prompt_path),
            "artifacts": self.artifacts.to_dict(),
        }
        if self.model is not None:
            payload["model"] = self.model
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload


class ProviderInvocationError(ArgusError):
    def __init__(self, failure: ProviderFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


@dataclass(frozen=True, slots=True)
class ProviderResponse(Generic[T]):
    provider_name: str
    action_name: str
    payload: T
    raw_payload: object
    prompt_sha256: str
    artifacts: ProviderArtifacts
    exit_status: int
    timestamp: datetime
    model: str | None = None
    reasoning_effort: str | None = None

    def metadata_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider_name": self.provider_name,
            "action_name": self.action_name,
            "prompt_sha256": self.prompt_sha256,
            "exit_status": self.exit_status,
            "timestamp": _dump_timestamp(self.timestamp),
            "artifacts": self.artifacts.to_dict(),
        }
        if self.model is not None:
            payload["model"] = self.model
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload


class Provider(Protocol):
    name: str

    def run_action(
        self,
        *,
        action_name: ActionType | str,
        problem_spec: ProblemSpec,
        input_payload: Mapping[str, JSONValue],
        output_schema: StructuredOutputSchema[T],
    ) -> ProviderResponse[T]:
        ...
