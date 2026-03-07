from __future__ import annotations

import argparse
from collections import deque
import json
import os
from dataclasses import dataclass
import shutil
import sys
from collections.abc import Mapping, Sequence
from typing import Deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

from argus.benchmarks import BenchmarkHarness, render_benchmark_report
from argus.config import ArgusConfig, RunConfig
from argus.errors import ArgusError, ArgusUserError, ArgusValidationError
from argus.inspection import (
    build_run_status_summary,
    inspect_artifact_path,
    render_inspection_report,
    render_run_status_report,
    resolve_inspection_target,
)
from argus.models import LearningNote, LearningNoteType, OutcomeFeedback, OutcomeFeedbackStatus
from argus.providers import CodexProvider, GeminiProvider, OpenCodeProvider, Provider
from argus.search import SearchRuntime
from argus.storage import FileSystemStateStore
from argus.progress import FileProgressSink, ProgressEvent, ProgressSink

_PROVIDER_TYPES = {
    "codex": CodexProvider,
    "gemini": GeminiProvider,
    "opencode": OpenCodeProvider,
}

_PROGRESS_MODES = ("auto", "plain", "jsonl", "quiet")


_ACTION_LABELS: dict[str, str] = {
    "frame_problem": "Framing",
    "generate_seed": "Exploring",
    "stress_test": "Stress testing",
    "deepen": "Deepening",
    "mutate": "Iterating",
    "combine": "Combining",
    "migrate": "Cross-island transfer",
    "compress_learning": "Compressing learnings",
    "rank": "Selecting finalists",
}


@dataclass(frozen=True)
class _RunProgressMetadata:
    run_id: str
    request: str
    provider_pool: list[str]
    budget: int
    artifact_path: Path


class _ComposedProgressSink(ProgressSink):
    def __init__(self, sinks: Sequence[ProgressSink] | None = None):
        self._sinks: list[ProgressSink] = list(sinks or [])

    def emit(self, event: ProgressEvent) -> None:
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception:
                pass


class _NullProgressSink:
    def emit(self, event: ProgressEvent) -> None:
        del event


class _JsonlProgressSink(ProgressSink):
    def emit(self, event: ProgressEvent) -> None:
        print(json.dumps(event.to_dict(), sort_keys=True), file=sys.stderr, flush=True)


class _AutoProgressRenderer(ProgressSink):
    def __init__(
        self,
        metadata: _RunProgressMetadata,
        *,
        interactive: bool = False,
        verbose: bool = False,
    ):
        self._metadata = metadata
        self._interactive = interactive and sys.stderr.isatty()
        self._verbose = verbose
        self._recent_nodes: Deque[str] = deque(maxlen=5)
        self._start_perf: float | None = None
        self._current_stage = "initializing"
        self._nodes = 0
        self._frontier = 0
        self._archive = 0
        self._winners = 0
        self._step = 0
        self._spent = 0
        self._best_bet: str | None = None
        self._conservative: str | None = None
        self._high_upside: str | None = None
        self._rendered_line_count = 0

    def emit(self, event: ProgressEvent) -> None:
        payload = event.payload
        if self._start_perf is None:
            self._start_perf = time.perf_counter()

        self._step = event.step_count
        self._spent = event.budget_spent
        if "nodes" in payload:
            self._nodes = int(payload["nodes"])
        if "frontier" in payload:
            self._frontier = int(payload["frontier"])
        if "archive" in payload:
            self._archive = int(payload["archive"])
        if "winners" in payload:
            self._winners = int(payload["winners"])

        if event.kind == "run_started":
            budget = payload.get("budget")
            if isinstance(budget, int) and budget > 0:
                self._spent = 0
        if event.kind == "stage_started":
            self._current_stage = _format_stage_label(payload)
        elif event.kind == "stage_completed":
            self._current_stage = _format_stage_label(payload, suffix=" complete")
        elif event.kind == "run_completed":
            self._current_stage = "final selection complete"
            self._best_bet = _coerce_optional_str(payload.get("best_bet"))
            self._conservative = _coerce_optional_str(payload.get("conservative"))
            self._high_upside = _coerce_optional_str(payload.get("high_upside"))

        if event.kind in {"node_admitted", "node_rejected", "node_failed"}:
            self._recent_nodes.appendleft(_format_node_event(event))

        default_emit_kinds = {
            "run_started",
            "stage_started",
            "stage_completed",
            "node_admitted",
            "node_rejected",
            "node_failed",
            "frontier_refreshed",
            "selection_finalized",
            "run_completed",
            "run_failed",
        }
        verbose_emit_kinds = {
            "pairwise_round_started",
            "pairwise_decision",
            "provider_invocation",
            "provider_failed",
        }

        if event.kind in default_emit_kinds or (self._verbose and event.kind in verbose_emit_kinds):
            if self._verbose and event.kind in verbose_emit_kinds:
                self._recent_nodes.appendleft(_format_technical_event(event))
            self._emit(event)

        if event.kind in {"run_completed", "run_failed"}:
            if self._best_bet is not None:
                self._recent_nodes.appendleft(f"✅ best_bet={self._best_bet}")
            if self._conservative is not None:
                self._recent_nodes.appendleft(f"✅ conservative={self._conservative}")
            if self._high_upside is not None:
                self._recent_nodes.appendleft(f"✅ high_upside={self._high_upside}")

    def _emit(self, event: ProgressEvent) -> None:
        status_line = self._status_line(event)
        feed = [f"  {line}" for line in self._recent_nodes]

        if self._interactive:
            self._clear_rendered_block()
            block = "\n".join([status_line, *feed])
            print(block, file=sys.stderr)
            print("\r\x1b[2K", end="", file=sys.stderr, flush=True)
            self._rendered_line_count = 1 + len(feed)
            return

        print(status_line, file=sys.stderr)
        for line in feed:
            print(line, file=sys.stderr)

    def _clear_rendered_block(self) -> None:
        for _ in range(self._rendered_line_count):
            print("\x1b[1A\r\x1b[2K", end="", file=sys.stderr)

    def _status_line(self, event: ProgressEvent) -> str:
        start_perf = self._start_perf
        elapsed = 0.0 if start_perf is None else max(time.perf_counter() - start_perf, 0.0)
        current = _elapsed_seconds_to_mmss(elapsed)
        stage = self._current_stage
        if self._metadata.budget == 0:
            budget = "?"
        else:
            budget = str(self._metadata.budget)
        return (
            f"[{current}] Step {self._step}/{budget} • Nodes {self._nodes} • Frontier {self._frontier} "
            f"• Winners {self._winners} • Current: {stage}"
        )


def _format_stage_label(payload: Mapping[str, object], *, suffix: str = "") -> str:
    label = payload.get("label")
    if isinstance(label, str) and label.strip():
        return f"{label.strip()}{suffix}"
    action = payload.get("action")
    if isinstance(action, str):
        action_label = _ACTION_LABELS.get(action.strip(), action.strip())
        return f"{action_label}{suffix}"
    return "processing"


def _format_node_event(event: ProgressEvent) -> str:
    payload = event.payload
    node_id = payload.get("node_id")
    thesis = payload.get("thesis")
    selection_mode = payload.get("selection_mode")
    if not isinstance(node_id, str):
        node_id = "unknown"
    if not isinstance(thesis, str):
        thesis = ""
    snippet = thesis[:84] if len(thesis) <= 84 else f"{thesis[:81]}..."
    action_label = ""
    if isinstance(selection_mode, str) and selection_mode:
        action_label = f" [{selection_mode}]"
    if event.kind == "node_admitted":
        icon = "✓"
    elif event.kind == "node_rejected":
        icon = "✕"
    else:
        icon = "↗"
    return f"{icon} {node_id}{action_label} {snippet}" if snippet else f"{icon} {node_id}{action_label}"


def _elapsed_seconds_to_mmss(seconds: float) -> str:
    bounded = max(0.0, seconds)
    total = int(bounded)
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def _coerce_optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _format_technical_event(event: ProgressEvent) -> str:
    payload = event.payload
    if event.kind == "pairwise_round_started":
        objective = _coerce_optional_str(payload.get("objective")) or "selection"
        candidate_count = payload.get("candidate_count")
        if isinstance(candidate_count, int):
            return f"↷ Pairwise {objective}: {candidate_count} candidates"
        return f"↷ Pairwise {objective}"
    if event.kind == "pairwise_decision":
        left = _coerce_optional_str(payload.get("left_node_id")) or "a"
        right = _coerce_optional_str(payload.get("right_node_id")) or "b"
        winner = _coerce_optional_str(payload.get("winner_node_id")) or "unknown"
        return f"↷ {left} vs {right} → {winner}"
    if event.kind == "provider_invocation":
        action = _coerce_optional_str(payload.get("action")) or "provider action"
        provider = _coerce_optional_str(payload.get("provider")) or ""
        return f"→ {action}: {provider}" if provider else f"→ {action}"
    return event.kind


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argus",
        description="Argus: a Codex-first decision-and-invention engine.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root. Defaults to the current working directory.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Execute a single Argus search request.",
    )
    run_parser.add_argument(
        "request",
        nargs="?",
        default=None,
        help="Ambiguous request or problem statement.",
    )
    run_parser.add_argument(
        "--prompt-file",
        dest="prompt_file",
        type=Path,
        default=None,
        help=(
            "Optional file containing the run request text. Use this instead of the "
            "positional request argument."
        ),
    )
    run_parser.add_argument(
        "--budget",
        type=int,
        default=12,
        help="Maximum search steps to spend once the runtime is implemented.",
    )
    run_parser.add_argument(
        "--provider",
        default=None,
        help=(
            "Provider name or comma-separated provider pool. The first provider is the "
            "fallback default."
        ),
    )
    run_parser.add_argument(
        "--run-config",
        dest="run_config_path",
        type=Path,
        default=None,
        help=(
            "Optional TOML config path defining provider_pool and per-provider model overrides. "
            "If omitted, defaults to provider=codex. Explicit --provider overrides provider_pool."
        ),
    )
    run_parser.add_argument(
        "--progress",
        choices=_PROGRESS_MODES,
        default="auto",
        help=(
            "Progress mode: auto for tty/plain adaptation, plain line stream, "
            "jsonl raw event stream, or quiet."
        ),
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose internal progress details.",
    )
    run_parser.set_defaults(handler=_handle_run)

    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Validate run inputs without executing provider actions.",
    )
    dry_run_parser.add_argument(
        "request",
        nargs="?",
        default=None,
        help="Ambiguous request or problem statement.",
    )
    dry_run_parser.add_argument(
        "--prompt-file",
        dest="prompt_file",
        type=Path,
        default=None,
        help=(
            "Optional file containing the run request text. Use this instead of the "
            "positional request argument."
        ),
    )
    dry_run_parser.add_argument(
        "--budget",
        type=int,
        default=12,
        help="Search budget to validate for a future run invocation.",
    )
    dry_run_parser.add_argument(
        "--provider",
        default=None,
        help=(
            "Provider name or comma-separated provider pool. The first provider is the "
            "fallback default."
        ),
    )
    dry_run_parser.add_argument(
        "--run-config",
        dest="run_config_path",
        type=Path,
        default=None,
        help=(
            "Optional TOML config path defining provider_pool and per-provider model overrides. "
            "If omitted, defaults to provider=codex. Explicit --provider overrides provider_pool."
        ),
    )
    dry_run_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )
    dry_run_parser.set_defaults(handler=_handle_dry_run)

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Execute stored benchmark cases.",
    )
    benchmark_parser.add_argument(
        "--case",
        dest="case_name",
        default=None,
        help="Optional benchmark case identifier to run. Defaults to all stored cases.",
    )
    benchmark_parser.add_argument(
        "--provider",
        default=None,
        help=(
            "Provider name or comma-separated provider pool for benchmark actions. "
            "The first provider is the fallback default."
        ),
    )
    benchmark_parser.add_argument(
        "--run-config",
        dest="run_config_path",
        type=Path,
        default=None,
        help=(
            "Optional TOML config path defining provider_pool and per-provider model overrides. "
            "If omitted, defaults to provider=codex. Explicit --provider overrides provider_pool."
        ),
    )
    benchmark_parser.set_defaults(handler=_handle_benchmark)

    feedback_parser = subparsers.add_parser(
        "feedback",
        help="Record shipped outcome feedback for a persisted run node.",
    )
    feedback_parser.add_argument("run_id", help="Persisted Argus run id.")
    feedback_parser.add_argument(
        "--node",
        dest="node_id",
        required=True,
        help="Node id whose outcome you observed.",
    )
    feedback_parser.add_argument(
        "--outcome",
        choices=[status.value for status in OutcomeFeedbackStatus],
        required=True,
        help="Observed outcome status for the tested node.",
    )
    feedback_parser.add_argument(
        "--summary",
        required=True,
        help="Concise outcome summary for what actually happened.",
    )
    feedback_parser.add_argument(
        "--experiment",
        dest="experiment_label",
        default=None,
        help="Optional experiment label for operator audit.",
    )
    feedback_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Observed evidence line. Repeat for multiple facts.",
    )
    feedback_parser.add_argument(
        "--winning-pattern",
        action="append",
        default=[],
        help="Outcome-backed winning pattern to reuse later. Repeatable.",
    )
    feedback_parser.add_argument(
        "--failure-pattern",
        action="append",
        default=[],
        help="Outcome-backed failure pattern to reuse later. Repeatable.",
    )
    feedback_parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Constraint the outcome surfaced. Repeatable.",
    )
    feedback_parser.add_argument(
        "--routing-hint",
        action="append",
        default=[],
        help="Provider or search-routing lesson from the outcome. Repeatable.",
    )
    feedback_parser.add_argument(
        "--summary-note",
        action="append",
        default=[],
        help="Additional reusable summary note. Repeatable.",
    )
    feedback_parser.set_defaults(handler=_handle_feedback)

    status_parser = subparsers.add_parser(
        "status",
        help="Show progress for the latest or a selected Argus run.",
    )
    status_parser.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="Optional persisted Argus run id. Defaults to the latest run.",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )
    status_parser.add_argument(
        "--watch",
        action="store_true",
        help="Refresh status repeatedly until the run is complete.",
    )
    status_parser.set_defaults(handler=_handle_status)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect persisted Argus or Ralph-loop artifacts.",
    )
    inspect_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=None,
        help="Artifact path to inspect.",
    )
    inspect_parser.add_argument(
        "--latest-agent-run",
        action="store_true",
        help="Inspect the most recent Ralph-loop run under artifacts/agent_runs/.",
    )
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )
    inspect_parser.set_defaults(handler=_handle_inspect)

    observe_parser = subparsers.add_parser(
        "observe",
        help="Start a real-time observation server for an Argus run.",
    )
    observe_parser.add_argument(
        "run_id",
        nargs="?",
        default="latest",
        help="Optional persisted Argus run id. Defaults to the latest run.",
    )
    observe_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to run the observation server on.",
    )
    observe_parser.set_defaults(handler=_handle_observe)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ArgusConfig.discover(args.root)

    try:
        return args.handler(args, config)
    except ArgusUserError as exc:
        if sys.stderr.isatty():
            print(file=sys.stderr)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ArgusError as exc:
        if sys.stderr.isatty():
            print(file=sys.stderr)
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _handle_run(args: argparse.Namespace, config: ArgusConfig) -> int:
    if args.budget <= 0:
        raise ArgusUserError("--budget must be a positive integer.")

    request = _resolve_run_request(args)

    run_config = _load_run_config(args.run_config_path)
    provider_names = _resolve_provider_names(
        provider_arg=args.provider,
        run_config=run_config,
    )
    state_store = FileSystemStateStore(config.runs_dir)
    run_id = state_store.allocate_run_id()
    providers = [
        _build_provider(
            config,
            provider_name,
            model=None if run_config is None else run_config.provider_model(provider_name),
        )
        for provider_name in provider_names
    ]
    metadata = _RunProgressMetadata(
        run_id=run_id,
        request=request,
        provider_pool=provider_names,
        budget=args.budget,
        artifact_path=state_store.root_dir / run_id,
    )
    sink = _build_progress_sink(
        run_id=run_id,
        metadata=metadata,
        mode=args.progress,
        verbose=args.verbose,
        state_store=state_store,
    )
    _print_run_header(metadata)
    provider = providers[0]
    runtime = SearchRuntime(
        provider=provider,
        providers=providers,
        state_store=state_store,
        progress_sink=sink,
        progress_verbose=args.verbose,
    )
    result = runtime.run(
        request=request,
        budget=args.budget,
        run_id=run_id,
    )
    elapsed = result.manifest.updated_at - result.manifest.created_at
    _print_run_recap(result=result, metadata=metadata, elapsed=elapsed)
    print(result.summary_markdown.rstrip())
    return 0


def _handle_dry_run(args: argparse.Namespace, config: ArgusConfig) -> int:
    if args.budget <= 0:
        raise ArgusUserError("--budget must be a positive integer.")

    request = _resolve_run_request(args)
    run_config = _load_run_config(args.run_config_path)
    provider_names = _resolve_provider_names(
        provider_arg=args.provider,
        run_config=run_config,
    )
    _validate_provider_binaries(provider_names)
    providers = [
        _build_provider(
            config,
            provider_name,
            model=None if run_config is None else run_config.provider_model(provider_name),
        )
        for provider_name in provider_names
    ]

    payload: dict[str, object] = {
        "status": "ok",
        "request_source": "prompt_file" if args.prompt_file is not None else "inline",
        "request_chars": len(request),
        "budget": args.budget,
        "provider_pool": provider_names,
        "provider_models": {
            provider.name: getattr(provider, "model", None)
            for provider in providers
        },
    }
    if args.run_config_path is not None:
        payload["run_config_path"] = str(args.run_config_path.expanduser().resolve())
    if args.prompt_file is not None:
        payload["prompt_file"] = str(args.prompt_file.expanduser().resolve())

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("dry_run=ok")
    print(f"request_source={payload['request_source']}")
    print(f"request_chars={payload['request_chars']}")
    print(f"budget={payload['budget']}")
    print("provider_pool=" + ",".join(provider_names))
    for provider in providers:
        print(f"provider_model[{provider.name}]={getattr(provider, 'model', None)}")
    if "run_config_path" in payload:
        print(f"run_config_path={payload['run_config_path']}")
    if "prompt_file" in payload:
        print(f"prompt_file={payload['prompt_file']}")
    return 0


def _handle_benchmark(args: argparse.Namespace, config: ArgusConfig) -> int:
    run_config = _load_run_config(args.run_config_path)
    provider_names = _resolve_provider_names(
        provider_arg=args.provider,
        run_config=run_config,
    )
    providers = [
        _build_provider(
            config,
            provider_name,
            model=None if run_config is None else run_config.provider_model(provider_name),
        )
        for provider_name in provider_names
    ]
    provider = providers[0]
    harness = BenchmarkHarness(
        provider=provider,
        providers=providers,
        state_store=FileSystemStateStore(config.runs_dir),
        cases_dir=config.benchmark_cases_dir,
        output_root=config.benchmark_runs_dir,
        latest_pointer=config.latest_benchmark_run_pointer,
    )
    result = harness.run(case_name=args.case_name)
    print(render_benchmark_report(result))
    return 0 if result.manifest.failed_count == 0 else 1


def _handle_feedback(args: argparse.Namespace, config: ArgusConfig) -> int:
    store = FileSystemStateStore(config.runs_dir)
    persisted_run = store.load_run(args.run_id)
    if persisted_run.state is None:
        raise ArgusUserError(
            f"Run {args.run_id!r} has no persisted search state to attach feedback to."
        )
    node_id = args.node_id.strip()
    if not node_id:
        raise ArgusUserError("--node must not be empty.")
    node = persisted_run.state.nodes.get(node_id)
    if node is None:
        raise ArgusUserError(
            f"Run {persisted_run.manifest.run_id!r} does not contain node {node_id!r}."
        )
    summary = args.summary.strip()
    if not summary:
        raise ArgusUserError("--summary must not be empty.")

    recorded_at = datetime.now(timezone.utc)
    outcome_status = OutcomeFeedbackStatus(args.outcome)
    feedback = OutcomeFeedback(
        feedback_id=_allocate_feedback_id(store, recorded_at),
        run_id=persisted_run.manifest.run_id,
        node_id=node_id,
        candidate_thesis=node.candidate.thesis,
        problem_statement=persisted_run.problem_spec.request,
        outcome_status=outcome_status,
        summary=summary,
        learning_notes=_build_feedback_learning_notes(
            args=args,
            node_id=node_id,
            candidate_thesis=node.candidate.thesis,
            outcome_status=outcome_status,
            summary=summary,
        ),
        evidence=_normalize_cli_lines(args.evidence, flag_name="--evidence"),
        experiment_label=args.experiment_label,
        recorded_at=recorded_at,
    )
    refreshed_manifest, _, merged_memory = store.record_outcome_feedback(feedback)

    print(f"feedback_id={feedback.feedback_id}")
    print(f"run_id={feedback.run_id}")
    print(f"node_id={feedback.node_id}")
    print(f"outcome={feedback.outcome_status.value}")
    print(f"learning_notes={len(feedback.learning_notes)}")
    print(f"memory_entries={len(merged_memory.entries)}")
    print(f"run_path={store.root_dir / refreshed_manifest.run_id}")
    return 0


def _handle_inspect(args: argparse.Namespace, config: ArgusConfig) -> int:
    target = resolve_inspection_target(
        config,
        args.path,
        latest_agent_run=args.latest_agent_run or args.path is None,
    )
    summary = inspect_artifact_path(target)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_inspection_report(summary))
    return 0


def _handle_status(args: argparse.Namespace, config: ArgusConfig) -> int:
    if args.watch and args.json:
        raise ArgusUserError("--watch is not compatible with --json output.")

    if args.watch:
        return _handle_status_watch(args, config)

    summary = build_run_status_summary(config, run_id=args.run_id)
    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    else:
        print(
            render_run_status_report(
                summary,
                color=_supports_color_output(),
            )
        )
    return 0


def _handle_status_watch(args: argparse.Namespace, config: ArgusConfig) -> int:
    while True:
        summary = build_run_status_summary(config, run_id=args.run_id)
        if sys.stdout.isatty():
            print("\x1b[2J\x1b[H", end="", file=sys.stdout)
        print(
            render_run_status_report(
                summary,
                color=_supports_color_output(),
            )
        )
        if summary.status != "running":
            return 0
        time.sleep(0.5)


def _build_progress_sink(
    *,
    run_id: str,
    metadata: _RunProgressMetadata,
    mode: str,
    verbose: bool,
    state_store: FileSystemStateStore,
) -> _ComposedProgressSink | _JsonlProgressSink | _NullProgressSink:
    file_sink = FileProgressSink(state_store.progress_events_path(run_id))

    if mode == "quiet":
        return _ComposedProgressSink([file_sink])

    render = _AutoProgressRenderer(
        metadata,
        interactive=mode == "auto",
        verbose=verbose,
    )
    if mode == "plain":
        return _ComposedProgressSink([file_sink, render])
    if mode == "jsonl":
        return _ComposedProgressSink([file_sink, _JsonlProgressSink()])
    return _ComposedProgressSink([file_sink, render])


def _print_run_header(metadata: _RunProgressMetadata) -> None:
    request_line = metadata.request.strip().replace("\n", " ")
    if len(request_line) > 120:
        request_line = request_line[:117] + "..."
    print(f"Argus · {metadata.run_id}", file=sys.stderr)
    print(f"Request: {request_line}", file=sys.stderr)
    print(f"Providers: {', '.join(metadata.provider_pool)}", file=sys.stderr)
    print(f"Search budget: {metadata.budget} steps", file=sys.stderr)
    print(f"Artifacts: {metadata.artifact_path}", file=sys.stderr)
    print(
        f"Tip: watch with `uv run argus status {metadata.run_id}`",
        file=sys.stderr,
    )
    print(file=sys.stderr)


def _print_run_recap(
    *,
    result,
    metadata: _RunProgressMetadata,
    elapsed: timedelta,
) -> None:
    minutes, seconds = divmod(max(0, int(elapsed.total_seconds())), 60)
    best_bet = result.final_recommendation.best_bet_node_id
    conservative = result.final_recommendation.conservative_node_id
    high_upside = result.final_recommendation.high_upside_node_id
    print(f"Completed in {minutes:02d}:{seconds:02d}", file=sys.stderr)
    print(
        f"{'Best bet':12}  "
        f"{best_bet:10}  {_node_snippet(result.state, best_bet)}",
        file=sys.stderr,
    )
    print(
        f"{'Conservative':12}  "
        f"{_node_id_or_dash(conservative):10}  {_node_snippet(result.state, conservative)}",
        file=sys.stderr,
    )
    print(
        f"{'High-upside':12}  "
        f"{_node_id_or_dash(high_upside):10}  {_node_snippet(result.state, high_upside)}",
        file=sys.stderr,
    )
    print(f"{'Summary':12}  {metadata.artifact_path / 'summary.md'}", file=sys.stderr)
    print(file=sys.stderr)


def _handle_observe(args: argparse.Namespace, config: ArgusConfig) -> int:
    from argus.observe import start_observer_server
    start_observer_server(config, args.run_id, args.port)
    return 0


def _build_provider(
    config: ArgusConfig,
    provider_name: str,
    *,
    model: str | None = None,
) -> Provider:
    normalized_provider = provider_name.strip().lower()
    provider_type = _PROVIDER_TYPES.get(normalized_provider)
    if provider_type is None:
        supported = ", ".join(sorted(_PROVIDER_TYPES))
        raise ArgusUserError(
            f"Unknown provider {provider_name!r}. Supported providers: {supported}."
        )
    return provider_type(
        artifacts_root=config.provider_invocations_dir,
        model=model,
    )


def _resolve_provider_names(
    *,
    provider_arg: str | None,
    run_config: RunConfig | None,
) -> list[str]:
    if provider_arg is not None:
        return _parse_provider_names(provider_arg)
    if run_config is not None:
        return list(run_config.provider_pool)
    return ["codex"]


def _load_run_config(path: Path | None) -> RunConfig | None:
    if path is None:
        return None
    try:
        return RunConfig.load(path)
    except ArgusValidationError as exc:
        raise ArgusUserError(str(exc)) from exc


def _parse_provider_names(value: str) -> list[str]:
    if not isinstance(value, str):
        raise ArgusUserError("--provider must be a string.")
    provider_names: list[str] = []
    for raw_name in value.split(","):
        normalized_name = raw_name.strip().lower()
        if not normalized_name:
            continue
        if normalized_name not in provider_names:
            provider_names.append(normalized_name)
    if not provider_names:
        raise ArgusUserError("--provider must include at least one provider name.")
    return provider_names


def _validate_provider_binaries(provider_names: Sequence[str]) -> None:
    missing: list[str] = []
    for provider_name in provider_names:
        provider_type = _PROVIDER_TYPES.get(provider_name)
        if provider_type is None:
            continue
        binary = provider_type.default_binary
        if shutil.which(binary) is None:
            missing.append(f"{provider_name} (missing `{binary}` in PATH)")
    if missing:
        raise ArgusUserError(
            "Provider binaries not found: " + ", ".join(missing) + "."
        )


def _build_feedback_learning_notes(
    *,
    args: argparse.Namespace,
    node_id: str,
    candidate_thesis: str,
    outcome_status: OutcomeFeedbackStatus,
    summary: str,
) -> list[LearningNote]:
    notes: list[LearningNote] = []
    note_groups = (
        (LearningNoteType.WINNING_PATTERN, args.winning_pattern, "--winning-pattern"),
        (LearningNoteType.FAILURE_PATTERN, args.failure_pattern, "--failure-pattern"),
        (LearningNoteType.CONSTRAINT, args.constraint, "--constraint"),
        (LearningNoteType.ROUTING_HINT, args.routing_hint, "--routing-hint"),
        (LearningNoteType.SUMMARY, args.summary_note, "--summary-note"),
    )
    for note_type, raw_values, flag_name in note_groups:
        for text in _normalize_cli_lines(raw_values, flag_name=flag_name):
            notes.append(
                LearningNote(
                    note_type=note_type,
                    text=text,
                    source_node_ids=[node_id],
                )
            )
    if notes:
        return notes
    return [
        LearningNote(
            note_type=_default_feedback_note_type(outcome_status),
            text=_default_feedback_note_text(
                candidate_thesis=candidate_thesis,
                outcome_status=outcome_status,
                summary=summary,
            ),
            source_node_ids=[node_id],
        )
    ]


def _default_feedback_note_type(outcome_status: OutcomeFeedbackStatus) -> LearningNoteType:
    if outcome_status is OutcomeFeedbackStatus.VALIDATED:
        return LearningNoteType.WINNING_PATTERN
    if outcome_status is OutcomeFeedbackStatus.INVALIDATED:
        return LearningNoteType.FAILURE_PATTERN
    return LearningNoteType.SUMMARY


def _default_feedback_note_text(
    *,
    candidate_thesis: str,
    outcome_status: OutcomeFeedbackStatus,
    summary: str,
) -> str:
    outcome_label = outcome_status.value.replace("_", " ")
    return f'{outcome_label.title()} outcome for "{candidate_thesis}": {summary}'


def _normalize_cli_lines(values: Sequence[str], *, flag_name: str) -> list[str]:
    normalized: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if not value:
            raise ArgusUserError(f"{flag_name} entries must not be empty.")
        normalized.append(value)
    return normalized


def _allocate_feedback_id(
    store: FileSystemStateStore,
    recorded_at: datetime,
) -> str:
    existing_ids = {
        entry.feedback_id for entry in store.load_outcome_feedback_ledger().entries
    }
    base = recorded_at.strftime("feedback-%Y%m%dT%H%M%SZ")
    candidate = base
    index = 1
    while candidate in existing_ids:
        candidate = f"{base}-{index:02d}"
        index += 1
    return candidate


def _supports_color_output() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _resolve_run_request(args: argparse.Namespace) -> str:
    raw_request = args.request
    prompt_file = args.prompt_file

    has_inline_request = isinstance(raw_request, str) and raw_request.strip() != ""
    has_prompt_file = prompt_file is not None
    if has_inline_request and has_prompt_file:
        raise ArgusUserError(
            "Provide either positional request text or --prompt-file, not both."
        )
    if not has_inline_request and not has_prompt_file:
        raise ArgusUserError(
            "Provide request text or --prompt-file."
        )

    if has_prompt_file:
        assert prompt_file is not None
        resolved_path = prompt_file.expanduser().resolve()
        if not resolved_path.is_file():
            raise ArgusUserError(f"--prompt-file does not exist: {resolved_path}")
        text = resolved_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ArgusUserError("--prompt-file must contain non-empty request text.")
        return text

    assert isinstance(raw_request, str)
    normalized_request = raw_request.strip()
    if not normalized_request:
        raise ArgusUserError("request must not be empty.")
    return normalized_request


def _node_id_or_dash(node_id: str | None) -> str:
    return node_id if node_id else "-"


def _node_snippet(state: object, node_id: str | None) -> str:
    if state is None or node_id is None:
        return "n/a"
    candidate = getattr(state, "nodes", {}).get(node_id)
    if candidate is None:
        return "n/a"
    thesis = candidate.candidate.thesis.strip()
    if len(thesis) <= 58:
        return thesis
    return thesis[:55] + "..."
