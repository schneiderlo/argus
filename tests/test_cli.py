from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from argus.cli import (
    _AutoProgressRenderer,
    _RunProgressMetadata,
    _format_stage_label,
    _build_provider,
    build_parser,
    main,
)
from argus.progress import build_event
from argus.config import ArgusConfig
from argus.errors import ArgusUserError
from argus.inspection import ProviderInvocationSummary, RunStatusSummary, render_run_status_report
from argus.models import (
    ActionType,
    Candidate,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    SearchState,
)
from argus.providers import CodexProvider, GeminiProvider, OpenCodeProvider
from argus.search import SearchPolicy
from argus.storage import FileSystemStateStore, RunStatus
from tests.search_fixtures import SearchFixtureProvider


class CliTests(unittest.TestCase):
    def test_parser_exposes_expected_subcommands(self) -> None:
        parser = build_parser()
        subcommands = parser._subparsers._group_actions[0].choices
        self.assertEqual(
            set(subcommands),
            {"run", "dry-run", "benchmark", "feedback", "status", "inspect", "observe"},
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
                        "--progress",
                        "quiet",
                    ]
                )

            runs = sorted(
                path for path in (root / "artifacts" / "runs").iterdir() if path.is_dir()
            )
            self.assertEqual(exit_code, 0)
            self.assertIn("Completed in", stderr)
            self.assertIn("Argus Recommendation", stdout)
            self.assertNotIn("run_id=", stdout)
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0] / "final-recommendation.json").is_file())
            self.assertTrue((runs[0] / "routing-summary.json").is_file())
            self.assertTrue((runs[0] / "summary.md").is_file())

    def test_run_command_accepts_prompt_file_instead_of_positional_request(self) -> None:
        with TemporaryRepoRoot() as root:
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            prompt_path = root / "request.txt"
            prompt_path.write_text(
                "Find the best retention strategy for a workflow-heavy product.",
                encoding="utf-8",
            )
            with patch("argus.cli._build_provider", return_value=provider):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "run",
                        "--prompt-file",
                        str(prompt_path),
                        "--progress",
                        "quiet",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Completed in", stderr)
        self.assertIn("Argus Recommendation", stdout)

    def test_run_command_rejects_when_both_request_and_prompt_file_are_provided(self) -> None:
        with TemporaryRepoRoot() as root:
            prompt_path = root / "request.txt"
            prompt_path.write_text("Find the best retention strategy.", encoding="utf-8")
            exit_code, _, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "run",
                    "Inline request",
                    "--prompt-file",
                    str(prompt_path),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn(
            "Provide either positional request text or --prompt-file, not both.",
            stderr,
        )

    def test_run_command_rejects_missing_prompt_file(self) -> None:
        with TemporaryRepoRoot() as root:
            missing_path = root / "missing-request.txt"
            exit_code, _, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "run",
                    "--prompt-file",
                    str(missing_path),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("--prompt-file does not exist:", stderr)

    def test_run_command_rejects_empty_prompt_file(self) -> None:
        with TemporaryRepoRoot() as root:
            prompt_path = root / "empty-request.txt"
            prompt_path.write_text("   \n", encoding="utf-8")
            exit_code, _, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "run",
                    "--prompt-file",
                    str(prompt_path),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("--prompt-file must contain non-empty request text.", stderr)

    def test_dry_run_command_validates_inputs_and_prints_summary(self) -> None:
        with TemporaryRepoRoot() as root:
            run_config_path = root / "run-config.toml"
            _write_run_config_fixture(
                run_config_path,
                provider_pool=["codex", "gemini"],
                provider_models={
                    "codex": "gpt-5-codex",
                    "gemini": "gemini-3.1-pro-preview",
                },
            )
            prompt_path = root / "request.txt"
            prompt_path.write_text(
                "Find the best retention strategy for a workflow-heavy product.",
                encoding="utf-8",
            )
            with patch("argus.cli._validate_provider_binaries", return_value=None):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "dry-run",
                        "--run-config",
                        str(run_config_path),
                        "--prompt-file",
                        str(prompt_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("dry_run=ok", stdout)
        self.assertIn("request_source=prompt_file", stdout)
        self.assertIn("provider_pool=codex,gemini", stdout)
        self.assertIn("provider_model[codex]=gpt-5-codex", stdout)
        self.assertIn("provider_model[gemini]=gemini-3.1-pro-preview", stdout)

    def test_dry_run_command_supports_json_output(self) -> None:
        with TemporaryRepoRoot() as root:
            run_config_path = root / "run-config.toml"
            _write_run_config_fixture(
                run_config_path,
                provider_pool=["codex"],
                provider_models={"codex": "gpt-5-codex"},
            )
            with patch("argus.cli._validate_provider_binaries", return_value=None):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "dry-run",
                        "Find the best retention strategy.",
                        "--run-config",
                        str(run_config_path),
                        "--json",
                    ]
                )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["request_source"], "inline")
        self.assertEqual(payload["provider_pool"], ["codex"])
        self.assertEqual(payload["provider_models"]["codex"], "gpt-5-codex")

    def test_dry_run_command_reports_selected_cost_profile(self) -> None:
        with TemporaryRepoRoot() as root:
            with patch("argus.cli._validate_provider_binaries", return_value=None):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "dry-run",
                        "Find the best retention strategy.",
                        "--cost-profile",
                        "lean",
                        "--json",
                    ]
                )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["cost_profile"], "lean")
        self.assertEqual(payload["search_policy"]["seed_target"], 4)
        self.assertEqual(payload["search_policy"]["provider_max_concurrency"], 2)

    def test_dry_run_command_rejects_when_both_request_and_prompt_file_are_provided(self) -> None:
        with TemporaryRepoRoot() as root:
            prompt_path = root / "request.txt"
            prompt_path.write_text("Find the best retention strategy.", encoding="utf-8")
            exit_code, _, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "dry-run",
                    "Inline request",
                    "--prompt-file",
                    str(prompt_path),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn(
            "Provide either positional request text or --prompt-file, not both.",
            stderr,
        )

    def test_dry_run_command_rejects_invalid_budget(self) -> None:
        with TemporaryRepoRoot() as root:
            exit_code, _, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "dry-run",
                    "Find the best retention strategy.",
                    "--budget",
                    "0",
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("--budget must be a positive integer.", stderr)

    def test_run_command_uses_provider_pool_and_models_from_run_config(self) -> None:
        with TemporaryRepoRoot() as root:
            run_config_path = root / "run-config.toml"
            _write_run_config_fixture(
                run_config_path,
                provider_pool=["codex", "gemini"],
                provider_models={
                    "codex": "codex-test-model",
                    "gemini": "gemini-test-model",
                },
            )
            built: list[tuple[str, str | None]] = []

            def _build_provider_with_capture(
                config: ArgusConfig,
                provider_name: str,
                *,
                model: str | None = None,
            ):
                built.append((provider_name, model))
                return SearchFixtureProvider(
                    root / "artifacts" / "provider_invocations" / provider_name,
                    name=provider_name,
                )

            with patch(
                "argus.cli._build_provider",
                side_effect=_build_provider_with_capture,
            ):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "run",
                        "Find the best retention strategy.",
                        "--budget",
                        "9",
                        "--run-config",
                        str(run_config_path),
                        "--progress",
                        "quiet",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Argus ·", stderr)
        self.assertIn("Completed in", stderr)
        self.assertIn("Argus Recommendation", stdout)
        self.assertEqual(
            built,
            [
                ("codex", "codex-test-model"),
                ("gemini", "gemini-test-model"),
            ],
        )

    def test_run_command_provider_flag_overrides_run_config_provider_pool(self) -> None:
        with TemporaryRepoRoot() as root:
            run_config_path = root / "run-config.toml"
            _write_run_config_fixture(
                run_config_path,
                provider_pool=["codex", "gemini"],
                provider_models={
                    "codex": "codex-test-model",
                    "gemini": "gemini-test-model",
                    "opencode": "opencode-test-model",
                },
            )
            built: list[tuple[str, str | None]] = []

            def _build_provider_with_capture(
                config: ArgusConfig,
                provider_name: str,
                *,
                model: str | None = None,
            ):
                built.append((provider_name, model))
                return SearchFixtureProvider(
                    root / "artifacts" / "provider_invocations" / provider_name,
                    name=provider_name,
                )

            with patch(
                "argus.cli._build_provider",
                side_effect=_build_provider_with_capture,
            ):
                exit_code, _, stderr = _run_cli(
                [
                        "--root",
                        str(root),
                        "run",
                        "Find the best retention strategy.",
                        "--budget",
                        "9",
                        "--run-config",
                        str(run_config_path),
                        "--provider",
                        "opencode",
                        "--progress",
                        "quiet",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Completed in", stderr)
        self.assertEqual(
            built,
            [("opencode", "opencode-test-model")],
        )

    def test_run_command_passes_cost_profile_policy_to_runtime(self) -> None:
        with TemporaryRepoRoot() as root:
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            captured: dict[str, object] = {}

            class StubRuntime:
                def __init__(self, **kwargs):
                    captured["policy"] = kwargs.get("policy")

                def run(self, *, request: str, budget: int, run_id: str):
                    del request, budget, run_id
                    return SimpleNamespace(
                        manifest=SimpleNamespace(
                            created_at=datetime(2026, 3, 7, tzinfo=timezone.utc),
                            updated_at=datetime(2026, 3, 7, 0, 0, 5, tzinfo=timezone.utc),
                        ),
                        final_recommendation=SimpleNamespace(
                            best_bet_node_id="node-0001",
                            conservative_node_id=None,
                            high_upside_node_id=None,
                        ),
                        state=SimpleNamespace(
                            nodes={
                                "node-0001": SimpleNamespace(
                                    candidate=SimpleNamespace(
                                        thesis="Lean profile candidate."
                                    )
                                )
                            }
                        ),
                        summary_markdown="Argus Recommendation",
                    )

            with patch("argus.cli._build_provider", return_value=provider), patch(
                "argus.cli.SearchRuntime",
                StubRuntime,
            ):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "run",
                        "Find the best retention strategy.",
                        "--cost-profile",
                        "lean",
                        "--progress",
                        "quiet",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Cost profile: lean", stderr)
        policy = captured["policy"]
        self.assertIsInstance(policy, SearchPolicy)
        self.assertEqual(policy.seed_target, 4)
        self.assertEqual(policy.provider_max_concurrency, 2)
        self.assertIn("Argus Recommendation", stdout)

    def test_run_command_jsonl_mode_emits_progress_events(self) -> None:
        with TemporaryRepoRoot() as root:
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            with patch("argus.cli._build_provider", return_value=provider):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "run",
                        "Find the best retention strategy.",
                        "--progress",
                        "jsonl",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Argus Recommendation", stdout)
        event_lines = [
            line
            for line in stderr.splitlines()
            if line.strip().startswith("{\"")
        ]
        self.assertTrue(event_lines)
        parsed = json.loads(event_lines[0])
        self.assertIn("kind", parsed)
        self.assertIn(parsed["kind"], {"run_started", "run_completed", "run_failed"})

    def test_interactive_progress_renderer_clears_stale_text(self) -> None:
        metadata = _RunProgressMetadata(
            run_id="run-20260307T000000Z",
            request="Run for progress rendering checks.",
            provider_pool=["codex"],
            budget=12,
            cost_profile="standard",
            artifact_path=Path("/tmp"),
        )
        renderer = _AutoProgressRenderer(metadata, interactive=True)
        renderer._interactive = True
        buffer = io.StringIO()
        with patch("argus.cli.sys.stderr", buffer):
            renderer.emit(
                build_event(
                    kind="run_started",
                    run_id=metadata.run_id,
                    step_count=0,
                    budget_spent=0,
                    timestamp=datetime(2026, 3, 7, tzinfo=timezone.utc),
                    payload={"budget": 12},
                )
            )
            renderer.emit(
                build_event(
                    kind="stage_started",
                    run_id=metadata.run_id,
                    step_count=1,
                    budget_spent=0,
                    timestamp=datetime(2026, 3, 7, 1, tzinfo=timezone.utc),
                    payload={"label": "Exploring"},
                )
            )

        output = buffer.getvalue()
        self.assertIn("Current: initializing", output)
        self.assertIn("Current: Exploring", output)
        self.assertNotIn("Current: Exploringing", output)

    def test_interactive_progress_renderer_rewinds_multiline_blocks(self) -> None:
        metadata = _RunProgressMetadata(
            run_id="run-20260307T000000Z",
            request="Run for multiline progress rendering checks.",
            provider_pool=["codex"],
            budget=12,
            cost_profile="standard",
            artifact_path=Path("/tmp"),
        )
        renderer = _AutoProgressRenderer(metadata, interactive=True)
        renderer._interactive = True
        buffer = io.StringIO()
        with patch("argus.cli.sys.stderr", buffer):
            renderer.emit(
                build_event(
                    kind="run_started",
                    run_id=metadata.run_id,
                    step_count=0,
                    budget_spent=0,
                    timestamp=datetime(2026, 3, 7, tzinfo=timezone.utc),
                    payload={"budget": 12},
                )
            )
            renderer.emit(
                build_event(
                    kind="node_rejected",
                    run_id=metadata.run_id,
                    step_count=1,
                    budget_spent=1,
                    timestamp=datetime(2026, 3, 7, 1, tzinfo=timezone.utc),
                    payload={
                        "node_id": "node-0002",
                        "selection_mode": "balanced",
                        "thesis": "First rejected thesis.",
                    },
                )
            )
            renderer.emit(
                build_event(
                    kind="node_admitted",
                    run_id=metadata.run_id,
                    step_count=1,
                    budget_spent=1,
                    timestamp=datetime(2026, 3, 7, 1, 0, 1, tzinfo=timezone.utc),
                    payload={
                        "node_id": "node-0003",
                        "selection_mode": "balanced",
                        "thesis": "Second admitted thesis.",
                    },
                )
            )

        output = buffer.getvalue()
        self.assertIn("\x1b[1A", output)
        self.assertIn("node-0002", output)
        self.assertIn("node-0003", output)

    def test_stage_label_formatter_maps_runtime_actions_to_display_labels(self) -> None:
        self.assertEqual(_format_stage_label({"action": "generate_seed"}), "Exploring")
        self.assertEqual(
            _format_stage_label({"action": "generate_seed"}, suffix=" complete"),
            "Exploring complete",
        )
        self.assertEqual(_format_stage_label({"action": "rank"}), "Selecting finalists")

    def test_stage_completed_progress_uses_friendly_labels(self) -> None:
        metadata = _RunProgressMetadata(
            run_id="run-20260307T000000Z",
            request="Run for stage label checks.",
            provider_pool=["codex"],
            budget=12,
            cost_profile="standard",
            artifact_path=Path("/tmp"),
        )
        renderer = _AutoProgressRenderer(metadata)
        buffer = io.StringIO()
        with patch("argus.cli.sys.stderr", buffer):
            renderer.emit(
                build_event(
                    kind="run_started",
                    run_id=metadata.run_id,
                    step_count=0,
                    budget_spent=0,
                    timestamp=datetime(2026, 3, 7, tzinfo=timezone.utc),
                    payload={"budget": 12},
                )
            )
            renderer.emit(
                build_event(
                    kind="stage_completed",
                    run_id=metadata.run_id,
                    step_count=1,
                    budget_spent=1,
                    timestamp=datetime(2026, 3, 7, 1, tzinfo=timezone.utc),
                    payload={
                        "action": "generate_seed",
                        "nodes": 10,
                        "archive": 5,
                        "frontier": 2,
                    },
                )
            )

        output = buffer.getvalue()
        self.assertIn("Current: Exploring complete", output)

    def test_run_command_plain_progress_mode_prints_line_feed(self) -> None:
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
                        "--progress",
                        "plain",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Argus Recommendation", stdout)
        self.assertIn("Argus ·", stderr)
        self.assertIn("Completed in", stderr)
        self.assertNotIn("Provider routing", stdout)

    def test_status_command_watch_mode_runs_to_completion(self) -> None:
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
                run_id="run-watch-complete",
            )
            store.save_snapshot(
                manifest.run_id,
                state=_feedback_ready_state(),
                status=RunStatus.COMPLETED,
            )

            exit_code, stdout, stderr = _run_cli(
                ["--root", str(root), "status", "run-watch-complete", "--watch"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("run_id=run-watch-complete", stdout)
        self.assertIn("status=completed", stdout)

    def test_run_command_emits_immediate_progress_header_and_tailored_recap(self) -> None:
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

        self.assertEqual(exit_code, 0)
        self.assertIn("Argus Recommendation", stdout)
        self.assertIn("Argus ·", stderr)
        self.assertIn("Completed in", stderr)
        self.assertNotIn("Provider routing", stdout)

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

    def test_benchmark_command_uses_provider_pool_and_models_from_run_config(self) -> None:
        with TemporaryRepoRoot() as root:
            _write_benchmark_case_fixture(
                root / "benchmarks" / "cases" / "product-strategy-retention.json"
            )
            run_config_path = root / "run-config.toml"
            _write_run_config_fixture(
                run_config_path,
                provider_pool=["codex", "gemini"],
                provider_models={
                    "codex": "codex-test-model",
                    "gemini": "gemini-test-model",
                },
            )
            built: list[tuple[str, str | None]] = []

            def _build_provider_with_capture(
                config: ArgusConfig,
                provider_name: str,
                *,
                model: str | None = None,
            ):
                built.append((provider_name, model))
                return SearchFixtureProvider(
                    root / "artifacts" / "provider_invocations" / provider_name,
                    name=provider_name,
                )

            with patch(
                "argus.cli._build_provider",
                side_effect=_build_provider_with_capture,
            ):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "benchmark",
                        "--case",
                        "product-strategy-retention",
                        "--run-config",
                        str(run_config_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("benchmark_session=", stdout)
        self.assertEqual(
            built,
            [
                ("codex", "codex-test-model"),
                ("gemini", "gemini-test-model"),
            ],
        )

    def test_benchmark_command_passes_cost_profile_policy_to_harness(self) -> None:
        with TemporaryRepoRoot() as root:
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            captured: dict[str, object] = {}

            class StubHarness:
                def __init__(self, **kwargs):
                    captured["policy"] = kwargs.get("policy")

                def run(self, *, case_name: str | None = None):
                    del case_name
                    return SimpleNamespace(
                        manifest=SimpleNamespace(failed_count=0)
                    )

            with patch("argus.cli._build_provider", return_value=provider), patch(
                "argus.cli.BenchmarkHarness",
                StubHarness,
            ), patch(
                "argus.cli.render_benchmark_report",
                return_value="benchmark_session=stub",
            ):
                exit_code, stdout, stderr = _run_cli(
                    [
                        "--root",
                        str(root),
                        "benchmark",
                        "--cost-profile",
                        "max",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("benchmark_session=stub", stdout)
        policy = captured["policy"]
        self.assertIsInstance(policy, SearchPolicy)
        self.assertEqual(policy.seed_target, 12)
        self.assertEqual(policy.combine_limit, 2)
        self.assertEqual(policy.provider_max_concurrency, 6)

    def test_run_command_rejects_invalid_run_config(self) -> None:
        with TemporaryRepoRoot() as root:
            run_config_path = root / "run-config.toml"
            run_config_path.write_text(
                "provider_pool = []\n",
                encoding="utf-8",
            )
            exit_code, _, stderr = _run_cli(
                [
                    "--root",
                    str(root),
                    "run",
                    "Find the best retention strategy.",
                    "--run-config",
                    str(run_config_path),
                ]
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("provider_pool must include at least one provider.", stderr)

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

    def test_status_report_supports_colorized_rendering(self) -> None:
        report = render_run_status_report(
            RunStatusSummary(
                run_id="run-color",
                status="running",
                provider_name="codex",
                created_at="2026-03-06T19:35:59Z",
                updated_at="2026-03-06T19:44:46Z",
                request="Build a wasm language.",
                budget=12,
                budget_spent=7,
                step_count=8,
                node_count=10,
                archive_count=6,
                frontier_count=6,
                pruned_count=1,
                winner_count=0,
                current_action="deepen",
                active_provider_invocation_count=1,
                active_provider_invocations=[
                    ProviderInvocationSummary(
                        invocation_id="20260306T194446367393Z-deepen",
                        action_name="deepen",
                        state="running",
                        started_at="2026-03-06T19:44:46Z",
                        pid=1234,
                        elapsed="00:31",
                    )
                ],
                recent_provider_invocations=[],
            ),
            color=True,
        )

        self.assertIn("Argus Run Status", report)
        self.assertIn("\x1b[", report)
        self.assertIn("current_action=", report)


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


def _write_run_config_fixture(
    path: Path,
    *,
    provider_pool: list[str],
    provider_models: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "provider_pool = [" + ", ".join(f'"{name}"' for name in provider_pool) + "]",
        "",
    ]
    for provider_name, model in provider_models.items():
        lines.extend(
            [
                f"[providers.{provider_name}]",
                f'model = "{model}"',
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


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
