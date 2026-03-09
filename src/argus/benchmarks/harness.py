from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from argus.benchmarks.dataset import load_benchmark_cases, select_benchmark_cases
from argus.benchmarks.models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkRuntimeMode,
    BenchmarkRunManifest,
    BenchmarkStatus,
)
from argus.errors import ArgusValidationError
from argus.models import FinalRecommendation, ProblemSpec, SearchState
from argus.providers import Provider
from argus.search import ResearchRuntime, SearchPolicy, SearchRuntime, StagedResearchRuntime
from argus.storage import FileSystemStateStore


@dataclass(frozen=True, slots=True)
class BenchmarkRunResult:
    session_dir: Path
    manifest: BenchmarkRunManifest


class BenchmarkHarness:
    def __init__(
        self,
        *,
        provider: Provider | None = None,
        providers: Mapping[str, Provider] | Sequence[Provider] | None = None,
        state_store: FileSystemStateStore,
        cases_dir: Path,
        output_root: Path,
        latest_pointer: Path | None = None,
        policy: SearchPolicy | None = None,
        runtime_modes: Sequence[BenchmarkRuntimeMode | str] | None = None,
    ) -> None:
        self._providers = self._normalize_provider_pool(
            provider=provider,
            providers=providers,
        )
        self._provider = (
            next(iter(self._providers.values()))
            if provider is None
            else self._providers[provider.name]
        )
        self._state_store = state_store
        self._cases_dir = cases_dir.expanduser().resolve()
        self._output_root = output_root.expanduser().resolve()
        self._latest_pointer = (
            latest_pointer.expanduser().resolve()
            if latest_pointer is not None
            else self._output_root / "latest.txt"
        )
        self._policy = policy
        self._runtime_modes = self._normalize_runtime_modes(runtime_modes)

    def _normalize_provider_pool(
        self,
        *,
        provider: Provider | None,
        providers: Mapping[str, Provider] | Sequence[Provider] | None,
    ) -> dict[str, Provider]:
        normalized: dict[str, Provider] = {}
        if providers is not None:
            provider_items: Sequence[tuple[str, Provider]]
            if isinstance(providers, Mapping):
                provider_items = list(providers.items())
            else:
                provider_items = [(pool_provider.name, pool_provider) for pool_provider in providers]
            for provider_name, pool_provider in provider_items:
                if not hasattr(pool_provider, "name") or not callable(
                    getattr(pool_provider, "run_action", None)
                ):
                    raise ArgusValidationError(
                        "providers entries must implement the Provider protocol."
                    )
                if provider_name in normalized:
                    raise ArgusValidationError(
                        f"providers contains duplicate provider names: {provider_name}."
                    )
                if provider_name != pool_provider.name:
                    raise ArgusValidationError(
                        "providers keys must match each provider's name."
                    )
                normalized[provider_name] = pool_provider
        if provider is not None:
            normalized.setdefault(provider.name, provider)
        if not normalized:
            raise ArgusValidationError("BenchmarkHarness requires at least one provider.")
        return normalized

    def _normalize_runtime_modes(
        self,
        runtime_modes: Sequence[BenchmarkRuntimeMode | str] | None,
    ) -> tuple[BenchmarkRuntimeMode, ...]:
        raw_modes = (
            [
                BenchmarkRuntimeMode.ADAPTIVE,
                BenchmarkRuntimeMode.STAGED,
                BenchmarkRuntimeMode.RESEARCH,
            ]
            if runtime_modes is None
            else list(runtime_modes)
        )
        normalized: list[BenchmarkRuntimeMode] = []
        for index, mode in enumerate(raw_modes):
            try:
                normalized_mode = (
                    mode
                    if isinstance(mode, BenchmarkRuntimeMode)
                    else BenchmarkRuntimeMode(str(mode).strip())
                )
            except ValueError as exc:
                supported = ", ".join(item.value for item in BenchmarkRuntimeMode)
                raise ArgusValidationError(
                    f"runtime_modes[{index}] must be one of: {supported}."
                ) from exc
            if normalized_mode in normalized:
                raise ArgusValidationError(
                    f"runtime_modes contains duplicate values: {normalized_mode.value}."
                )
            normalized.append(normalized_mode)
        if not normalized:
            raise ArgusValidationError("runtime_modes must include at least one item.")
        return tuple(normalized)

    def run(self, *, case_name: str | None = None) -> BenchmarkRunResult:
        cases = load_benchmark_cases(self._cases_dir)
        selected_cases = select_benchmark_cases(cases, case_name=case_name)
        previous_manifest = self._load_previous_manifest()
        previous_digests = {
            (result.case_id, result.runtime_mode): result.output_digest
            for result in ([] if previous_manifest is None else previous_manifest.case_results)
            if result.output_digest is not None
        }

        created_at = datetime.now(timezone.utc)
        session_id = self._allocate_session_id(created_at)
        session_dir = self._output_root / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        (session_dir / "cases").mkdir()

        runtimes = {
            runtime_mode: self._build_runtime(runtime_mode)
            for runtime_mode in self._runtime_modes
        }
        case_results: list[BenchmarkCaseResult] = []
        overall_status = BenchmarkStatus.COMPLETED
        for case in selected_cases:
            case_dir = session_dir / "cases" / case.case_id
            case_dir.mkdir(parents=True, exist_ok=False)
            _write_json(case_dir / "case.json", case.to_dict())
            for runtime_mode in self._runtime_modes:
                case_results.append(
                    self._run_case(
                        runtime=runtimes[runtime_mode],
                        runtime_mode=runtime_mode,
                        session_id=session_id,
                        session_dir=session_dir,
                        case=case,
                        case_dir=case_dir,
                        previous_output_digest=previous_digests.get(
                            (case.case_id, runtime_mode)
                        ),
                    )
                )
                if case_results[-1].status is BenchmarkStatus.FAILED:
                    overall_status = BenchmarkStatus.FAILED

        manifest = BenchmarkRunManifest(
            session_id=session_id,
            provider_name=self._provider.name,
            runtime_modes=list(self._runtime_modes),
            status=overall_status,
            created_at=created_at,
            cases_dir=str(self._cases_dir),
            previous_session_id=None if previous_manifest is None else previous_manifest.session_id,
            case_results=case_results,
        )
        _write_json(session_dir / "manifest.json", manifest.to_dict())
        self._latest_pointer.parent.mkdir(parents=True, exist_ok=True)
        self._latest_pointer.write_text(str(session_dir), encoding="utf-8")
        return BenchmarkRunResult(session_dir=session_dir, manifest=manifest)

    def _build_runtime(self, runtime_mode: BenchmarkRuntimeMode) -> SearchRuntime:
        runtime_cls: type[SearchRuntime]
        if runtime_mode is BenchmarkRuntimeMode.RESEARCH:
            runtime_cls = ResearchRuntime
        elif runtime_mode is BenchmarkRuntimeMode.STAGED:
            runtime_cls = StagedResearchRuntime
        else:
            runtime_cls = SearchRuntime
        return runtime_cls(
            provider=self._provider,
            providers=self._providers,
            state_store=self._state_store,
            policy=self._policy,
            # Keep benchmark outputs comparable across sessions instead of letting
            # prior runs change the stored fixture behavior.
            reuse_learning_memory=False,
        )

    def _run_case(
        self,
        *,
        runtime: SearchRuntime,
        runtime_mode: BenchmarkRuntimeMode,
        session_id: str,
        session_dir: Path,
        case: BenchmarkCase,
        case_dir: Path,
        previous_output_digest: str | None,
    ) -> BenchmarkCaseResult:
        mode_dir = case_dir / runtime_mode.value
        mode_dir.mkdir(parents=True, exist_ok=False)

        run_id = f"{session_id}-{case.case_id}-{runtime_mode.value}"
        run_path = self._state_store.root_dir / run_id
        benchmark_problem_spec = ProblemSpec(
            request=case.problem_spec.request,
            constraints=list(case.problem_spec.constraints),
            success_criteria=list(case.problem_spec.success_criteria),
            context={
                **case.problem_spec.context,
                "benchmark_case_id": case.case_id,
                "benchmark_family": case.family.value,
            },
        )

        try:
            search_result = runtime.run_problem(
                problem_spec=benchmark_problem_spec,
                budget=case.budget,
                run_id=run_id,
            )
        except Exception as exc:
            failure_payload = {
                "error": str(exc),
                "failure_type": type(exc).__name__,
                "runtime_mode": runtime_mode.value,
                "run_id": run_id,
                "run_path": str(run_path),
            }
            _write_json(mode_dir / "failure.json", failure_payload)
            result = BenchmarkCaseResult(
                case_id=case.case_id,
                family=case.family,
                runtime_mode=runtime_mode,
                status=BenchmarkStatus.FAILED,
                run_id=run_id,
                run_path=str(run_path),
                previous_output_digest=previous_output_digest,
                changed_from_previous=None,
                error=str(exc),
                failure_type=type(exc).__name__,
            )
            _write_json(mode_dir / "result.json", result.to_dict())
            return result

        summary_relative_path = Path("cases") / case.case_id / runtime_mode.value / "summary.md"
        final_relative_path = (
            Path("cases") / case.case_id / runtime_mode.value / "final-recommendation.json"
        )
        (session_dir / summary_relative_path).write_text(
            search_result.summary_markdown,
            encoding="utf-8",
        )
        _write_json(
            session_dir / final_relative_path,
            search_result.final_recommendation.to_dict(),
        )
        digest = _final_recommendation_digest(search_result.final_recommendation)
        result = BenchmarkCaseResult(
            case_id=case.case_id,
            family=case.family,
            runtime_mode=runtime_mode,
            status=BenchmarkStatus.COMPLETED,
            run_id=search_result.manifest.run_id,
            run_path=str(search_result.run_path),
            output_digest=digest,
            previous_output_digest=previous_output_digest,
            changed_from_previous=(
                None if previous_output_digest is None else digest != previous_output_digest
            ),
            best_bet_node_id=search_result.final_recommendation.best_bet_node_id,
            best_bet_thesis=_node_thesis(
                search_result.state,
                search_result.final_recommendation.best_bet_node_id,
            ),
            conservative_node_id=search_result.final_recommendation.conservative_node_id,
            conservative_thesis=_optional_node_thesis(
                search_result.state,
                search_result.final_recommendation.conservative_node_id,
            ),
            high_upside_node_id=search_result.final_recommendation.high_upside_node_id,
            high_upside_thesis=_optional_node_thesis(
                search_result.state,
                search_result.final_recommendation.high_upside_node_id,
            ),
            summary_path=str(summary_relative_path),
            final_recommendation_path=str(final_relative_path),
        )
        _write_json(mode_dir / "result.json", result.to_dict())
        return result

    def _allocate_session_id(self, created_at: datetime) -> str:
        self._output_root.mkdir(parents=True, exist_ok=True)
        base = created_at.strftime("benchmark-%Y%m%dT%H%M%SZ").lower()
        candidate = base
        index = 1
        while (self._output_root / candidate).exists():
            candidate = f"{base}-{index:02d}"
            index += 1
        return candidate

    def _load_previous_manifest(self) -> BenchmarkRunManifest | None:
        if not self._latest_pointer.is_file():
            return None

        target_text = self._latest_pointer.read_text(encoding="utf-8").strip()
        if not target_text:
            return None
        manifest_path = Path(target_text).expanduser().resolve() / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return BenchmarkRunManifest.from_dict(payload)


def render_benchmark_report(result: BenchmarkRunResult) -> str:
    lines = [
        f"benchmark_session={result.manifest.session_id}",
        f"session_path={result.session_dir}",
        f"status={result.manifest.status.value}",
        f"runtime_modes={','.join(mode.value for mode in result.manifest.runtime_modes)}",
        f"cases={result.manifest.case_count}",
        f"mode_runs={result.manifest.mode_result_count}",
        f"completed_case_modes={result.manifest.completed_mode_count}",
        f"failed_case_modes={result.manifest.failed_mode_count}",
    ]
    for case_result in sorted(
        result.manifest.case_results,
        key=lambda item: (item.case_id, item.runtime_mode.value),
    ):
        if case_result.status is BenchmarkStatus.COMPLETED:
            change_flag = (
                "n/a"
                if case_result.changed_from_previous is None
                else ("changed" if case_result.changed_from_previous else "unchanged")
            )
            lines.append(
                f"{case_result.case_id}[{case_result.runtime_mode.value}]: completed "
                f"run_id={case_result.run_id} "
                f"digest={case_result.output_digest[:12]} change_vs_previous={change_flag}"
            )
            continue
        lines.append(
            f"{case_result.case_id}[{case_result.runtime_mode.value}]: failed "
            f"failure_type={case_result.failure_type} "
            f"error={case_result.error}"
        )
    return "\n".join(lines)


def _final_recommendation_digest(final_recommendation: FinalRecommendation) -> str:
    payload = json.dumps(final_recommendation.to_dict(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _node_thesis(state: SearchState, node_id: str) -> str:
    return state.nodes[node_id].candidate.thesis


def _optional_node_thesis(state: SearchState, node_id: str | None) -> str | None:
    if node_id is None:
        return None
    return _node_thesis(state, node_id)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
