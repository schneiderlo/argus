from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from argus.cli import build_parser, main
from argus.models import ProblemSpec
from argus.storage import FileSystemStateStore
from tests.search_fixtures import SearchFixtureProvider


class CliTests(unittest.TestCase):
    def test_parser_exposes_expected_subcommands(self) -> None:
        parser = build_parser()
        subcommands = parser._subparsers._group_actions[0].choices
        self.assertEqual(set(subcommands), {"run", "benchmark", "inspect"})

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

            runs = sorted((root / "artifacts" / "runs").iterdir())
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Argus Recommendation", stdout)
            self.assertIn("run_id=", stdout)
            self.assertIn("best_bet=", stdout)
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0] / "final-recommendation.json").is_file())
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
