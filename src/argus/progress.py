from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
import json

from argus.models import JSONValue


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    kind: str
    run_id: str
    timestamp: datetime
    step_count: int
    budget_spent: int
    payload: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue | str | int]:
        return {
            "kind": self.kind,
            "run_id": self.run_id,
            "timestamp": self.timestamp.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "step_count": self.step_count,
            "budget_spent": self.budget_spent,
            "payload": dict(self.payload),
        }


class ProgressSink(Protocol):
    def emit(self, event: ProgressEvent) -> None:
        ...


class NullProgressSink:
    def emit(self, event: ProgressEvent) -> None:
        del event


@dataclass
class _JsonlWriter:
    path: Path

    def write_event(self, event: ProgressEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(event.to_dict(), sort_keys=True)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(serialized)
            output.write("\n")


class FileProgressSink:
    def __init__(self, path: Path):
        self._writer = _JsonlWriter(path)

    def emit(self, event: ProgressEvent) -> None:
        self._writer.write_event(event)


def _normalize_progress_payload(
    payload: Mapping[str, JSONValue] | None,
) -> dict[str, JSONValue]:
    if payload is None:
        return {}
    return dict(payload)


def build_event(
    *,
    kind: str,
    run_id: str,
    step_count: int,
    budget_spent: int,
    timestamp: datetime,
    payload: Mapping[str, JSONValue] | None = None,
) -> ProgressEvent:
    return ProgressEvent(
        kind=kind,
        run_id=run_id,
        timestamp=timestamp,
        step_count=step_count,
        budget_spent=budget_spent,
        payload=_normalize_progress_payload(payload),
    )
