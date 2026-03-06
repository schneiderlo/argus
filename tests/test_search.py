from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from argus.errors import ArgusValidationError
from argus.search import SearchPolicy, SearchRuntime
from argus.storage import FileSystemStateStore, RunStatus
from tests.search_fixtures import SearchFixtureProvider


class SearchRuntimeTests(unittest.TestCase):
    def test_runtime_executes_search_loop_and_persists_final_recommendation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            runtime = SearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    seed_target=4,
                    stress_test_limit=2,
                    deepen_limit=2,
                    mutate_limit=1,
                    combine_limit=1,
                    frontier_limit=4,
                    rejected_limit=2,
                    max_learning_notes=2,
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=9,
                run_id="run-search-fixture",
            )
            loaded = store.load_run("run-search-fixture")

        action_names = [call["action_name"] for call in provider.calls]
        self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
        self.assertEqual(loaded.manifest.status, RunStatus.COMPLETED)
        self.assertEqual(loaded.final_recommendation, result.final_recommendation)
        self.assertEqual(result.final_recommendation.best_bet_node_id, "node-0006")
        self.assertEqual(result.final_recommendation.conservative_node_id, "node-0003")
        self.assertEqual(result.final_recommendation.high_upside_node_id, "node-0004")
        self.assertEqual(result.state.winner_ids, ["node-0006", "node-0003", "node-0004"])
        self.assertEqual(len(result.state.learning_notes), 2)
        self.assertIn("node-0005", result.state.pruned_ids)
        self.assertIn("Argus Recommendation", result.summary_markdown)
        self.assertIn("frame_problem", action_names)
        self.assertIn("generate_seed", action_names)
        self.assertIn("stress_test", action_names)
        self.assertIn("deepen", action_names)
        self.assertIn("mutate", action_names)
        self.assertIn("combine", action_names)
        self.assertIn("compress_learning", action_names)
        self.assertGreaterEqual(action_names.count("evaluate_candidate"), 6)
        self.assertGreaterEqual(action_names.count("assess_novelty"), 3)

    def test_runtime_marks_manifest_failed_when_frame_problem_raises(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations",
                fail_on_action="frame_problem",
            )
            runtime = SearchRuntime(provider=provider, state_store=store)

            with self.assertRaises(ArgusValidationError):
                runtime.run(
                    request="Find the best architecture for a local-first system.",
                    budget=4,
                    run_id="run-frame-failure",
                )

            loaded = store.load_run("run-frame-failure")

        self.assertEqual(loaded.manifest.status, RunStatus.FAILED)
        self.assertIsNone(loaded.state)
        self.assertEqual(loaded.manifest.metadata["failed_action"], "frame_problem")
        self.assertIn("frame_problem", loaded.manifest.error)
