from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from argus.benchmarks import BenchmarkHarness, render_benchmark_report
from argus.config import ArgusConfig
from argus.errors import ArgusError, ArgusUserError
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

_PROVIDER_TYPES = {
    "codex": CodexProvider,
    "gemini": GeminiProvider,
    "opencode": OpenCodeProvider,
}


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
    run_parser.add_argument("request", help="Ambiguous request or problem statement.")
    run_parser.add_argument(
        "--budget",
        type=int,
        default=12,
        help="Maximum search steps to spend once the runtime is implemented.",
    )
    run_parser.add_argument(
        "--provider",
        default="codex",
        help=(
            "Provider name or comma-separated provider pool. The first provider is the "
            "fallback default. Defaults to codex."
        ),
    )
    run_parser.set_defaults(handler=_handle_run)

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
        default="codex",
        help=(
            "Provider name or comma-separated provider pool for benchmark actions. "
            "The first provider is the fallback default. Defaults to codex."
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ArgusConfig.discover(args.root)

    try:
        return args.handler(args, config)
    except ArgusUserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ArgusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _handle_run(args: argparse.Namespace, config: ArgusConfig) -> int:
    if args.budget <= 0:
        raise ArgusUserError("--budget must be a positive integer.")

    request = args.request.strip()
    if not request:
        raise ArgusUserError("request must not be empty.")

    provider_names = _parse_provider_names(args.provider)
    providers = [_build_provider(config, provider_name) for provider_name in provider_names]
    provider = providers[0]
    runtime = SearchRuntime(
        provider=provider,
        providers=providers,
        state_store=FileSystemStateStore(config.runs_dir),
    )
    result = runtime.run(
        request=request,
        budget=args.budget,
    )
    print(result.summary_markdown.rstrip())
    print()
    print(f"run_id={result.manifest.run_id}")
    print(f"run_path={result.run_path}")
    print(f"best_bet={result.final_recommendation.best_bet_node_id}")
    print(f"conservative={result.final_recommendation.conservative_node_id}")
    print(f"high_upside={result.final_recommendation.high_upside_node_id}")
    return 0


def _handle_benchmark(args: argparse.Namespace, config: ArgusConfig) -> int:
    provider_names = _parse_provider_names(args.provider)
    providers = [_build_provider(config, provider_name) for provider_name in provider_names]
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


def _build_provider(config: ArgusConfig, provider_name: str) -> Provider:
    normalized_provider = provider_name.strip().lower()
    provider_type = _PROVIDER_TYPES.get(normalized_provider)
    if provider_type is None:
        supported = ", ".join(sorted(_PROVIDER_TYPES))
        raise ArgusUserError(
            f"Unknown provider {provider_name!r}. Supported providers: {supported}."
        )
    return provider_type(artifacts_root=config.provider_invocations_dir)


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
