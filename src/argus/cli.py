from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from argus.config import ArgusConfig
from argus.errors import ArgusNotImplementedError, ArgusUserError
from argus.inspection import (
    inspect_artifact_path,
    render_inspection_report,
    resolve_inspection_target,
)


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
        help="Provider name to route actions through. Defaults to codex.",
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
        help="Optional benchmark case identifier to run once the harness exists.",
    )
    benchmark_parser.set_defaults(handler=_handle_benchmark)

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
    except ArgusNotImplementedError as exc:
        print(f"not implemented: {exc}", file=sys.stderr)
        return 1


def _handle_run(args: argparse.Namespace, _: ArgusConfig) -> int:
    if args.budget <= 0:
        raise ArgusUserError("--budget must be a positive integer.")

    request = args.request.strip()
    if not request:
        raise ArgusUserError("request must not be empty.")

    raise ArgusNotImplementedError(
        "Search execution is scaffolded but not wired yet. Remaining work items are "
        "the provider adapter, deterministic evaluator, novelty filter, "
        "search runtime, and final answer compilation."
    )


def _handle_benchmark(_: argparse.Namespace, __: ArgusConfig) -> int:
    raise ArgusNotImplementedError(
        "Benchmark execution is scaffolded but not wired yet. Implement the benchmark "
        "fixtures and harness before this command can run cases."
    )


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
