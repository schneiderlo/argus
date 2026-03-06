from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from argus.cli import build_parser, main
from argus.models import ProblemSpec
from argus.storage import FileSystemStateStore


class CliTests(unittest.TestCase):
    def test_parser_exposes_expected_subcommands(self) -> None:
        parser = build_parser()
        subcommands = parser._subparsers._group_actions[0].choices
        self.assertEqual(set(subcommands), {"run", "benchmark", "inspect"})

    def test_run_command_fails_explicitly_until_runtime_exists(self) -> None:
        exit_code, _, stderr = _run_cli(["run", "Find the best retention strategy."])

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "Search execution is scaffolded but not wired yet.",
            stderr,
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
