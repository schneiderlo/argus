from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
import json
from typing import Any

from argus.providers.base import ProviderArtifacts, StructuredOutputSchema
from argus.providers.cli_base import CliProviderBase, _ResponseExtractionError


class OpenCodeProvider(CliProviderBase):
    name = "opencode"
    prompt_worker_name = "OpenCode"
    default_binary = "opencode"
    command_display_name = "opencode run"
    model_env_var = "OPENCODE_MODEL"

    def _build_command(
        self,
        *,
        artifacts: ProviderArtifacts,
        prompt_text: str,
        output_schema: StructuredOutputSchema[Any],
    ) -> list[str]:
        command = [
            self.binary,
            "run",
            "--format",
            "json",
            "--dir",
            str(artifacts.sandbox_dir),
            prompt_text,
        ]
        if self.model is not None:
            command[2:2] = ["--model", self.model]
        return command

    def _extract_response_text(
        self,
        *,
        artifacts: ProviderArtifacts,
        stdout_text: str,
        stderr_text: str,
    ) -> str:
        events = _parse_json_events(stdout_text)
        if not events:
            raise _ResponseExtractionError(
                error_type="missing_output",
                message="opencode run completed without producing JSON events.",
            )

        full_messages: list[str] = []
        updated_parts: OrderedDict[str, str] = OrderedDict()
        part_fragments: list[str] = []

        for event in events:
            for assistant_message in _assistant_messages_from_event(event):
                if assistant_message:
                    full_messages.append(assistant_message)

            event_name = _event_name(event)
            if event_name == "message.part.updated":
                payload = _event_payload(event)
                if isinstance(payload, Mapping):
                    part = payload.get("part")
                    text = _text_from_part(part)
                    part_id = _part_id(part)
                    if text is not None and part_id is not None:
                        updated_parts[part_id] = text
            if event_name == "message.part.delta":
                payload = _event_payload(event)
                if isinstance(payload, Mapping):
                    delta = payload.get("delta")
                    field = payload.get("field")
                    if isinstance(delta, str) and _is_text_delta_field(field):
                        part_fragments.append(delta)

        if full_messages:
            return full_messages[-1]
        if updated_parts:
            return "".join(updated_parts.values())
        if part_fragments:
            return "".join(part_fragments)

        raise _ResponseExtractionError(
            error_type="missing_output",
            message="opencode JSON events did not include an assistant text response.",
        )


def _parse_json_events(stdout_text: str) -> list[Mapping[str, Any]]:
    stripped = stdout_text.strip()
    if not stripped:
        return []

    lines = [line for line in stdout_text.splitlines() if line.strip()]
    parsed: list[Mapping[str, Any]] = []
    if len(lines) == 1:
        parsed.extend(_coerce_event_document(lines[0]))
        return parsed

    for line in lines:
        parsed.extend(_coerce_event_document(line))
    return parsed


def _coerce_event_document(document: str) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(document)
    except json.JSONDecodeError as exc:
        raise _ResponseExtractionError(
            error_type="invalid_json",
            message=f"opencode run emitted invalid JSON: {exc}",
        ) from exc

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        return [payload]
    raise _ResponseExtractionError(
        error_type="invalid_json",
        message="opencode run emitted a non-object JSON event.",
    )


def _assistant_messages_from_event(event: Mapping[str, Any]) -> list[str]:
    messages: list[str] = []
    for mapping in _candidate_mappings(event):
        direct = _message_text(mapping)
        if direct is not None:
            messages.append(direct)

        message_value = mapping.get("message")
        if isinstance(message_value, Mapping):
            nested = _message_text(message_value)
            if nested is not None:
                messages.append(nested)
    return messages


def _candidate_mappings(event: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield event
    for key in ("data", "payload", "properties"):
        value = event.get(key)
        if isinstance(value, Mapping):
            yield value


def _message_text(value: Mapping[str, Any]) -> str | None:
    role = value.get("role")
    if role == "assistant":
        text = _coerce_assistant_text(value)
        if text:
            return text

    info = value.get("info")
    if isinstance(info, Mapping) and info.get("role") == "assistant":
        text = _parts_text(value.get("parts"))
        if text:
            return text
    return None


def _coerce_assistant_text(message: Mapping[str, Any]) -> str | None:
    for key in ("content", "text", "response"):
        value = message.get(key)
        if isinstance(value, str) and value:
            return value
    return _parts_text(message.get("parts"))


def _parts_text(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for part in value:
        text = _text_from_part(part)
        if text is not None:
            parts.append(text)
    return "".join(parts) if parts else None


def _text_from_part(part: object) -> str | None:
    if not isinstance(part, Mapping):
        return None
    part_type = part.get("type")
    if isinstance(part_type, str) and part_type not in {"text", "reasoning"}:
        return None
    for key in ("text", "content", "delta"):
        value = part.get(key)
        if isinstance(value, str):
            return value
    return None


def _part_id(part: object) -> str | None:
    if not isinstance(part, Mapping):
        return None
    for key in ("id", "partID", "part_id"):
        value = part.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event_name(event: Mapping[str, Any]) -> str | None:
    for mapping in _candidate_mappings(event):
        for key in ("type", "event", "name"):
            value = mapping.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _event_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("data", "payload", "properties"):
        value = event.get(key)
        if isinstance(value, Mapping):
            return value
    return event


def _is_text_delta_field(value: object) -> bool:
    if not isinstance(value, str):
        return True
    normalized = value.strip().lower()
    if not normalized:
        return True
    return normalized in {"text", "content"} or normalized.endswith(".text")
