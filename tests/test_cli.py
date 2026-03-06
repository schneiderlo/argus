from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from argus.cli import _build_provider, build_parser, main
from argus.config import ArgusConfig
from argus.errors import ArgusUserError
from argus.models import (
    ActionType,
    Candidate,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    SearchState,
)
from argus.providers import CodexProvider, GeminiProvider, OpenCodeProvider
from argus.storage import FileSystemStateStore, RunStatus
from tests.search_fixtures import SearchFixtureProvider


class CliTests(unittest.TestCase):
    def test_parser_exposes_expected_subcommands(self) -> None:
        parser = build_parser()
        subcommands = parser._subparsers._group_actions[0].choices
        self.assertEqual(
            set(subcommands),
            {"run", "benchmark", "feedback", "status", "inspect"},
        )

    def test_build_provider_supports_codex_gemini_and_opencode(self) -> None:
        with TemporaryRepoRoot() as root:
            config = ArgusConfig.discover(root)

            self.assertIsInstance(_build_provider(config, "codex"), CodexProvider)
            self.assertIsInstance(_build_provider(config, "gemini"), GeminiProvider)
            self.assertIsInstance(_build_provider(config, "opencode"), OpenCodeProvider)

    def test_build_provider_rejects_unknown_provider_with_supported_list(self) -> None:
        with TemporaryRepoRoot() as root:
            config = ArgusConfig.discover(root)

            with self.assertRaises(ArgusUserError) as captured:
                _build_provider(config, "unknown-provider")

        self.assertIn("codex, gemini, opencode", str(captured.exception))

    def test_run_command_executes_search_and_persists_artifacts(self) -> None:
        with TemporaryRepoRoot() as root:
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            with patch("argus.cli._build_provider", return_value=provider):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "run",
                        "Find the best retention strategy.",
                        "--budget",
                        "9",
                    ]
                )

            runs = sorted(
                path for path in (root / "artifacts" / "runs").iterdir() if path.is_dir()
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Argus Recommendation", stdout)
            self.assertIn("run_id=", stdout)
            self.assertIn("best_bet=", stdout)
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0] / "final-recommendation.json").is_file())
            self.assertTrue((runs[0] / "routing-summary.json").is_file())
            self.assertTrue((runs[0] / "summary.md").is_file())

    def test_benchmark_command_executes_selected_case_and_persists_session(self) -> None:
        with TemporaryRepoRoot() as root:
            _write_benchmark_case_fixture(
                root / "benchmarks" / "cases" / "product-strategy-retention.json"
            )
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            with patch("argus.cli._build_provider", return_value=provider):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "benchmark",
                        "--case",
                        "product-strategy-retention",
                    ]
                )

            sessions = sorted(
                path for path in (root / "artifacts" / "benchmarks").iterdir() if path.is_dir()
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("benchmark_session=", stdout)
            self.assertIn("completed_cases=1", stdout)
            self.assertIn("product-strategy-retention: completed", stdout)
            self.assertEqual(len(sessions), 1)
            self.assertTrue((sessions[0] / "manifest.json").is_file())
            self.assertTrue(
                (
                    sessions[0]
                    / "cases"
                    / "product-strategy-retention"
                    / "result.json"
                ).is_file()
            )

    def test_inspect_latest_agent_run_reads_pointer_and_metadata(self) -> None:
        with TemporaryRepoRoot() as root:
            run_dir = root / "artifacts" / "agent_runs" / "20260306T020456Z-iter-0001"
            run_dir.mkdir(parents=True)
            (run_dir / "prompt.md").write_text("prompt", encoding="utf-8")
            (run_dir / "verify.txt").write_text("ok", encoding="utf-8")
            (run_dir / "metadata.env").write_text(
                "iteration=1\nverify_exit=0\n",
                encoding="utf-8",
            )
            (root / "artifacts" / "latest-run.txt").write_text(
                str(run_dir),
                encoding="utf-8",
            )

            exit_code, stdout, _ = _run_cli(["--root", str(root), "inspect", "--json"])

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["target"], str(run_dir.resolve()))
        self.assertEqual(payload["metadata"]["iteration"], "1")
        self.assertIn("prompt.md", payload["recognized_artifacts"])
        self.assertIn("verify.txt", payload["recognized_artifacts"])

    def test_inspect_latest_agent_run_falls_back_to_newest_directory(self) -> None:
        with TemporaryRepoRoot() as root:
            older = root / "artifacts" / "agent_runs" / "older"
            newer = root / "artifacts" / "agent_runs" / "newer"
            older.mkdir(parents=True)
            newer.mkdir(parents=True)
            (older / "verify.txt").write_text("older", encoding="utf-8")
            (newer / "verify.txt").write_text("newer", encoding="utf-8")
            os.utime(older, ns=(1_000_000_000, 1_000_000_000))
            os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

            exit_code, stdout, _ = _run_cli(
                ["--root", str(root), "inspect", "--latest-agent-run"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn(f"target={newer.resolve()}", stdout)

    def test_inspect_requires_a_real_target(self) -> None:
        with TemporaryRepoRoot() as root:
            exit_code, _, stderr = _run_cli(
                ["--root", str(root), "inspect", "--latest-agent-run"]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("No agent-run artifacts found.", stderr)

    def test_inspect_argus_run_directory_reads_run_metadata(self) -> None:
        with TemporaryRepoRoot() as root:
            store = FileSystemStateStore(root / "artifacts" / "runs")
            manifest = store.create_run(
                problem_spec=ProblemSpec(
                    request="Find the best retention strategy.",
                    constraints=[],
                    success_criteria=["Increase activation."],
                    context={},
                ),
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020456Z",
            )
            run_dir = store.root_dir / manifest.run_id

            exit_code, stdout, _ = _run_cli(
                ["--root", str(root), "inspect", str(run_dir), "--json"]
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["kind"], "argus_run")
        self.assertEqual(payload["metadata"]["run_id"], "run-20260306T020456Z")
        self.assertEqual(payload["metadata"]["provider_name"], "codex")
        self.assertIn("run.json", payload["recognized_artifacts"])
        self.assertIn("problem-spec.json", payload["recognized_artifacts"])

    def test_feedback_command_persists_outcome_feedback_and_learning_memory(self) -> None:
        with TemporaryRepoRoot() as root:
            store = FileSystemStateStore(root / "artifacts" / "runs")
            manifest = store.create_run(
                problem_spec=ProblemSpec(
                    request="Find the best retention strategy.",
                    constraints=["Stay self-serve."],
                    success_criteria=["Increase activation."],
                    context={},
                ),
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020600Z",
            )
            store.save_snapshot(
                manifest.run_id,
                state=_feedback_ready_state(),
                status=RunStatus.COMPLETED,
            )

            exit_code, stdout, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "feedback",
                    manifest.run_id,
                    "--node",
                    "node-0002",
                    "--outcome",
                    "validated",
                    "--summary",
                    "Pilot teams kept returning because weekly review prep got faster.",
                    "--winning-pattern",
                    "Teams accept setup work when the audit trail saves recurring review time.",
                    "--evidence",
                    "4 of 5 pilot teams completed three weekly review cycles.",
                ]
            )

            run_dir = store.root_dir / manifest.run_id
            run_feedback_exists = (run_dir / "outcome-feedback.json").is_file()
            learning_memory_exists = (store.root_dir / "learning-memory.json").is_file()
            routing_stats = store.load_provider_routing_stats()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("feedback_id=feedback-", stdout)
        self.assertIn("outcome=validated", stdout)
        self.assertIn("learning_notes=1", stdout)
        self.assertTrue(run_feedback_exists)
        self.assertTrue(learning_memory_exists)
        self.assertTrue(
            any(
                entry.provider_name == "codex" and entry.action_name == "deepen"
                for entry in routing_stats.entries
            )
        )

    def test_status_command_defaults_to_latest_run_and_reports_progress(self) -> None:
        with TemporaryRepoRoot() as root:
            store = FileSystemStateStore(root / "artifacts" / "runs")
            older_manifest = store.create_run(
                problem_spec=ProblemSpec(
                    request="Older run.",
                    constraints=[],
                    success_criteria=["Finish."],
                    context={},
                ),
                provider_name="codex",
                budget=8,
                run_id="run-older",
            )
            store.save_snapshot(
                older_manifest.run_id,
                state=_feedback_ready_state(),
                status=RunStatus.COMPLETED,
            )
            latest_manifest = store.create_run(
                problem_spec=ProblemSpec(
                    request="Current run.",
                    constraints=["Stay local-first."],
                    success_criteria=["Show current progress."],
                    context={},
                ),
                provider_name="codex",
                budget=12,
                run_id="run-latest",
                created_at=datetime(2026, 3, 6, 2, 35, 59, tzinfo=timezone.utc),
            )
            latest_state = _feedback_ready_state()
            store.save_snapshot(
                latest_manifest.run_id,
                state=latest_state,
                status=RunStatus.RUNNING,
                updated_at=datetime(2026, 3, 6, 2, 44, 46, tzinfo=timezone.utc),
            )
            invocation_dir = (
                root
                / "artifacts"
                / "provider_invocations"
                / "20260306T024446367393Z-deepen"
            )
            invocation_dir.mkdir(parents=True)

            exit_code, stdout, stderr = _run_cli(
                ["--root", str(root), "status"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("run_id=run-latest", stdout)
        self.assertIn("status=running", stdout)
        self.assertIn("budget=2/12", stdout)
        self.assertIn("current_action=deepen", stdout)
        self.assertIn("active_provider_invocations=1", stdout)

    def test_status_command_supports_json_output_for_explicit_run(self) -> None:
        with TemporaryRepoRoot() as root:
            store = FileSystemStateStore(root / "artifacts" / "runs")
            manifest = store.create_run(
                problem_spec=ProblemSpec(
                    request="Inspect a completed run.",
                    constraints=[],
                    success_criteria=["Return status."],
                    context={},
                ),
                provider_name="codex",
                budget=12,
                run_id="run-json-status",
            )
            store.save_snapshot(
                manifest.run_id,
                state=_feedback_ready_state(),
                status=RunStatus.COMPLETED,
            )

            exit_code, stdout, stderr = _run_cli(
                ["--root", str(root), "status", manifest.run_id, "--json"]
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["run_id"], "run-json-status")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["provider_name"], "codex")
        self.assertEqual(payload["budget_spent"], 2)


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


class TemporaryRepoRoot:
    def __enter__(self) -> Path:
        from tempfile import TemporaryDirectory

        self._directory = TemporaryDirectory()
        return Path(self._directory.name)

    def __exit__(self, exc_type, exc, tb) -> None:
        self._directory.cleanup()


def _write_benchmark_case_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": "product-strategy-retention",
        "title": "Fixture benchmark case",
        "family": "product_strategy",
        "problem_spec": {
            "request": "Find the best retention strategy for a workflow-heavy product.",
            "constraints": [
                "Stay self-serve.",
                "Keep every decision auditable.",
            ],
            "success_criteria": [
                "Increase repeated use.",
                "Leave behind clear artifacts.",
            ],
            "context": {"segment": "product"},
        },
        "budget": 9,
        "evaluation_notes": [
            "Prefer durable workflow habits over decorative engagement loops.",
        ],
        "expected_qualities": [
            "Produce differentiated bets with explicit tradeoffs.",
        ],
        "tags": ["fixture", "retention"],
    }
    (path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _feedback_ready_state() -> SearchState:
    problem_spec = ProblemSpec(
        request="Find the best retention strategy.",
        constraints=["Stay self-serve."],
        success_criteria=["Increase activation."],
        context={},
    )
    root_node = Node(
        node_id="node-0001",
        parent_ids=[],
        depth=0,
        action_type=ActionType.FRAME_PROBLEM,
        provider_name="codex",
        candidate=Candidate(
            thesis="Frame the search around workflow-native retention.",
            mechanism="Bias the search toward repeatable operational rituals instead of decorative engagement loops.",
            assumptions=["Teams value repeated review workflows."],
            strengths=["Keeps the search grounded."],
            failure_modes=["Could overfit to existing habits."],
            unknowns=["How much setup teams will tolerate."],
            evidence=["The brief prioritizes activation over decorative usage."],
        ),
        novelty_score=1.0,
        lifecycle_status=NodeLifecycleStatus.ADMITTED,
        metadata={},
        created_at="2026-03-06T02:06:00Z",
    )
    candidate_node = Node(
        node_id="node-0002",
        parent_ids=["node-0001"],
        depth=1,
        action_type=ActionType.DEEPEN,
        provider_name="codex",
        candidate=Candidate(
            thesis="Workflow-native archive with weekly reviews",
            mechanism="Turn weekly review prep into a durable ritual by persisting the audit trail teams already need.",
            assumptions=["Teams already run weekly reviews."],
            strengths=["Creates a recurring retention hook."],
            failure_modes=["May add setup work before value is visible."],
            unknowns=["How quickly teams trust the audit trail."],
            evidence=["The product needs repeatable reasons to return."],
        ),
        novelty_score=0.78,
        lifecycle_status=NodeLifecycleStatus.ADMITTED,
        metadata={
            "provider_routing": {
                "assess_novelty": ["gemini"],
                "evaluate_candidate": ["opencode"],
            }
        },
        created_at="2026-03-06T02:08:00Z",
    )
    return SearchState(
        problem_spec=problem_spec,
        root_id="node-0001",
        nodes={
            "node-0001": root_node,
            "node-0002": candidate_node,
        },
        archive_ids=["node-0001", "node-0002"],
        frontier_ids=["node-0002"],
        pruned_ids=[],
        winner_ids=[],
        learning_notes=[],
        budget_spent=2,
        step_count=2,
    )
