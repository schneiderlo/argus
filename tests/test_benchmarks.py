from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from argus.benchmarks import BenchmarkFamily, BenchmarkHarness, BenchmarkStatus, load_benchmark_cases
from argus.search import SearchPolicy
from argus.storage import FileSystemStateStore
from tests.search_fixtures import SearchFixtureProvider


class BenchmarkDatasetTests(unittest.TestCase):
    def test_repository_fixture_set_covers_required_problem_families(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cases = load_benchmark_cases(repo_root / "benchmarks" / "cases")

        self.assertEqual(len(cases), 5)
        self.assertEqual(
            {case.family for case in cases},
            {
                BenchmarkFamily.PRODUCT_STRATEGY,
                BenchmarkFamily.GROWTH,
                BenchmarkFamily.UX,
                BenchmarkFamily.TECHNICAL_ARCHITECTURE,
                BenchmarkFamily.MONETIZATION,
            },
        )


class BenchmarkHarnessTests(unittest.TestCase):
    def test_harness_runs_cases_and_records_previous_output_digest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_benchmark_case_fixture(
                root / "benchmarks" / "cases" / "product-strategy-retention.json"
            )
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            harness = BenchmarkHarness(
                provider=provider,
                state_store=FileSystemStateStore(root / "artifacts" / "runs"),
                cases_dir=root / "benchmarks" / "cases",
                output_root=root / "artifacts" / "benchmarks",
                latest_pointer=root / "artifacts" / "benchmarks" / "latest.txt",
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

            first = harness.run(case_name="product-strategy-retention")
            second = harness.run(case_name="product-strategy-retention")

            first_case = first.manifest.case_results[0]
            second_case = second.manifest.case_results[0]

            self.assertEqual(first.manifest.status, BenchmarkStatus.COMPLETED)
            self.assertEqual(second.manifest.status, BenchmarkStatus.COMPLETED)
            self.assertIsNone(first_case.previous_output_digest)
            self.assertEqual(second_case.previous_output_digest, first_case.output_digest)
            self.assertFalse(second_case.changed_from_previous)
            self.assertEqual(second.manifest.previous_session_id, first.manifest.session_id)
            self.assertTrue((first.session_dir / "manifest.json").is_file())
            self.assertTrue(
                (
                    first.session_dir
                    / "cases"
                    / "product-strategy-retention"
                    / "final-recommendation.json"
                ).is_file()
            )
            self.assertTrue(
                (first.session_dir / "cases" / "product-strategy-retention" / "summary.md").is_file()
            )
            self.assertTrue((root / "artifacts" / "runs" / first_case.run_id).is_dir())
            self.assertEqual(
                (root / "artifacts" / "benchmarks" / "latest.txt").read_text(encoding="utf-8").strip(),
                str(second.session_dir),
            )


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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
