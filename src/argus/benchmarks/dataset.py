from __future__ import annotations

import json
from pathlib import Path

from argus.errors import ArgusUserError, ArgusValidationError

from argus.benchmarks.models import BenchmarkCase


def load_benchmark_cases(cases_dir: Path) -> list[BenchmarkCase]:
    resolved_dir = cases_dir.expanduser().resolve()
    if not resolved_dir.is_dir():
        raise ArgusUserError(f"Benchmark cases directory does not exist: {resolved_dir}")

    cases: list[BenchmarkCase] = []
    seen_case_ids: set[str] = set()
    for case_path in sorted(resolved_dir.glob("*.json")):
        case = _load_case_file(case_path)
        if case.case_id in seen_case_ids:
            raise ArgusValidationError(
                f"Duplicate benchmark case_id detected: {case.case_id}."
            )
        if case_path.stem != case.case_id:
            raise ArgusValidationError(
                f"Benchmark case filename {case_path.name!r} does not match case_id {case.case_id!r}."
            )
        seen_case_ids.add(case.case_id)
        cases.append(case)

    if not cases:
        raise ArgusUserError(f"No benchmark case fixtures found in {resolved_dir}")
    return cases


def select_benchmark_cases(
    cases: list[BenchmarkCase],
    *,
    case_name: str | None = None,
) -> list[BenchmarkCase]:
    if case_name is None:
        return list(cases)

    normalized_case_name = case_name.strip()
    for case in cases:
        if case.case_id == normalized_case_name:
            return [case]

    available = ", ".join(case.case_id for case in cases)
    raise ArgusUserError(
        f"Unknown benchmark case {case_name!r}. Available cases: {available}."
    )


def _load_case_file(case_path: Path) -> BenchmarkCase:
    try:
        payload = json.loads(case_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArgusValidationError(
            f"Benchmark case {case_path} does not contain valid JSON."
        ) from exc
    return BenchmarkCase.from_dict(payload)
