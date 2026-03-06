from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from argus.benchmarks import (
    EvaluatorBenchmarkCase,
    EvaluatorBenchmarkKind,
    load_evaluator_benchmark_cases,
)
from argus.eval import AgenticEvaluator, AgenticNoveltyFilter, rank_nodes
from argus.models import ActionType, ProblemSpec
from argus.providers import ProviderArtifacts, ProviderResponse

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EVALUATOR_CASES_DIR = _REPO_ROOT / "benchmarks" / "evaluator_cases"


class EvaluatorBenchmarkDatasetTests(unittest.TestCase):
    def test_repository_fixture_set_covers_required_judgment_modes_and_families(self) -> None:
        cases = load_evaluator_benchmark_cases(_EVALUATOR_CASES_DIR)

        self.assertEqual(len(cases), 7)
        self.assertEqual(
            {case.kind for case in cases},
            {
                EvaluatorBenchmarkKind.HARD_CONSTRAINT,
                EvaluatorBenchmarkKind.NOVELTY,
                EvaluatorBenchmarkKind.PAIRWISE,
                EvaluatorBenchmarkKind.RANKING,
            },
        )
        self.assertEqual(
            {case.family.value for case in cases},
            {
                "product_strategy",
                "growth",
                "ux",
                "technical_architecture",
                "monetization",
            },
        )

        novelty_outcomes = {
            case.expected_novelty.is_novel
            for case in cases
            if case.kind is EvaluatorBenchmarkKind.NOVELTY and case.expected_novelty is not None
        }
        self.assertEqual(novelty_outcomes, {False, True})

    def test_pairwise_objectives_include_a_conservative_and_high_upside_flip(self) -> None:
        cases = load_evaluator_benchmark_cases(_EVALUATOR_CASES_DIR)
        pairwise_cases = [case for case in cases if case.kind is EvaluatorBenchmarkKind.PAIRWISE]

        winners_by_objective = {
            case.objective.name: case.expected_pairwise.winner
            for case in pairwise_cases
            if case.objective is not None and case.expected_pairwise is not None
        }

        self.assertEqual(winners_by_objective["conservative_option"], "left")
        self.assertEqual(winners_by_objective["high_upside_option"], "right")
        self.assertIn("best_overall", winners_by_objective)


class EvaluatorBenchmarkExecutionTests(unittest.TestCase):
    def test_hard_constraint_benchmarks_drive_expected_evaluation_failures(self) -> None:
        for case in _cases_of_kind(EvaluatorBenchmarkKind.HARD_CONSTRAINT):
            with self.subTest(case=case.case_id), TemporaryDirectory() as directory:
                provider = BenchmarkFixtureProvider(case=case, root_dir=Path(directory))
                evaluator = AgenticEvaluator(provider=provider)

                result = evaluator.evaluate(case.problem_spec, case.candidate)

                self.assertEqual(result, case.expected_evaluation)
                self.assertFalse(result.score.hard_constraint_pass)
                self.assertEqual(provider.calls, ["evaluate_candidate"])

    def test_novelty_benchmarks_drive_duplicate_and_distinct_judgments(self) -> None:
        for case in _cases_of_kind(EvaluatorBenchmarkKind.NOVELTY):
            with self.subTest(case=case.case_id), TemporaryDirectory() as directory:
                provider = BenchmarkFixtureProvider(case=case, root_dir=Path(directory))
                novelty_filter = AgenticNoveltyFilter(provider=provider)

                result = novelty_filter.assess(
                    problem_spec=case.problem_spec,
                    candidate=case.candidate,
                    archive_nodes=[fixture.to_node() for fixture in case.archive_candidates],
                )

                self.assertEqual(result, case.expected_novelty)
                self.assertEqual(provider.calls, ["assess_novelty"])

    def test_pairwise_benchmarks_drive_objective_specific_winners(self) -> None:
        for case in _cases_of_kind(EvaluatorBenchmarkKind.PAIRWISE):
            with self.subTest(case=case.case_id), TemporaryDirectory() as directory:
                provider = BenchmarkFixtureProvider(case=case, root_dir=Path(directory))
                evaluator = AgenticEvaluator(provider=provider)

                result = evaluator.compare_nodes(
                    case.problem_spec,
                    case.left.to_node(),
                    case.right.to_node(),
                    objective=case.objective.name,
                    objective_description=case.objective.description,
                )

                self.assertEqual(result, case.expected_pairwise)
                self.assertEqual(provider.calls, ["rank"])

    def test_ranking_benchmarks_keep_hard_failures_behind_viable_nodes(self) -> None:
        for case in _cases_of_kind(EvaluatorBenchmarkKind.RANKING):
            with self.subTest(case=case.case_id):
                ranked = rank_nodes([node.to_node() for node in case.nodes])

                self.assertEqual([node.node_id for node in ranked], case.expected_rank_order)


class BenchmarkFixtureProvider:
    name = "benchmark-fixture"

    def __init__(self, *, case: EvaluatorBenchmarkCase, root_dir: Path) -> None:
        self.case = case
        self.root_dir = root_dir
        self.calls: list[str] = []

    def run_action(
        self,
        *,
        action_name: ActionType | str,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
        output_schema,
    ):
        normalized_action = action_name.value if isinstance(action_name, ActionType) else action_name
        self.calls.append(normalized_action)
        self._validate_problem_spec(problem_spec)

        if self.case.kind is EvaluatorBenchmarkKind.HARD_CONSTRAINT:
            self._validate_hard_constraint_call(normalized_action, input_payload)
            payload = self.case.expected_evaluation.to_dict()
        elif self.case.kind is EvaluatorBenchmarkKind.NOVELTY:
            self._validate_novelty_call(normalized_action, input_payload)
            payload = self.case.expected_novelty.to_dict()
        elif self.case.kind is EvaluatorBenchmarkKind.PAIRWISE:
            self._validate_pairwise_call(normalized_action, input_payload)
            payload = self.case.expected_pairwise.to_dict()
        else:
            raise AssertionError(f"Unexpected benchmark provider case kind: {self.case.kind}.")

        typed_payload = output_schema.validate(payload)
        artifacts = self._create_artifacts(normalized_action)
        _write_json(artifacts.schema_path, output_schema.json_schema)
        _write_json(artifacts.last_message_path, payload)
        _write_json(artifacts.response_path, payload)
        artifacts.prompt_path.write_text(f"fixture prompt for {self.case.case_id}\n", encoding="utf-8")
        artifacts.stdout_path.write_text("", encoding="utf-8")
        artifacts.stderr_path.write_text("", encoding="utf-8")
        _write_json(
            artifacts.metadata_path,
            {
                "provider_name": self.name,
                "action_name": normalized_action,
                "case_id": self.case.case_id,
                "status": "ok",
            },
        )

        return ProviderResponse(
            provider_name=self.name,
            action_name=normalized_action,
            payload=typed_payload,
            raw_payload=payload,
            prompt_sha256=f"fixture-{self.case.case_id}",
            artifacts=artifacts,
            exit_status=0,
            timestamp=self.case.left.to_node().created_at if self.case.left is not None else _fixture_time(),
            model="fixture-model",
        )

    def _validate_problem_spec(self, problem_spec: ProblemSpec) -> None:
        if problem_spec.to_dict() != self.case.problem_spec.to_dict():
            raise AssertionError(
                f"Unexpected problem_spec for {self.case.case_id}: {problem_spec.to_dict()!r}"
            )

    def _validate_hard_constraint_call(
        self,
        action_name: str,
        input_payload: dict[str, object],
    ) -> None:
        self._require_action(action_name, "evaluate_candidate")
        if input_payload.get("candidate") != self.case.candidate.to_dict():
            raise AssertionError(f"Unexpected candidate payload for {self.case.case_id}.")
        if "rubric" not in input_payload:
            raise AssertionError("Evaluator benchmark expected rubric in evaluate_candidate input.")

    def _validate_novelty_call(self, action_name: str, input_payload: dict[str, object]) -> None:
        self._require_action(action_name, "assess_novelty")
        if input_payload.get("candidate") != self.case.candidate.to_dict():
            raise AssertionError(f"Unexpected candidate payload for {self.case.case_id}.")
        expected_archive = [fixture.to_dict() for fixture in self.case.archive_candidates]
        if input_payload.get("archive_candidates") != expected_archive:
            raise AssertionError(f"Unexpected archive payload for {self.case.case_id}.")
        if "similarity_threshold" not in input_payload:
            raise AssertionError("Novelty benchmark expected similarity_threshold in input.")

    def _validate_pairwise_call(self, action_name: str, input_payload: dict[str, object]) -> None:
        self._require_action(action_name, "rank")
        if input_payload.get("objective") != self.case.objective.to_dict():
            raise AssertionError(f"Unexpected objective payload for {self.case.case_id}.")
        if input_payload.get("left") != self.case.left.to_dict():
            raise AssertionError(f"Unexpected left comparison payload for {self.case.case_id}.")
        if input_payload.get("right") != self.case.right.to_dict():
            raise AssertionError(f"Unexpected right comparison payload for {self.case.case_id}.")
        if "comparison_policy" not in input_payload:
            raise AssertionError("Pairwise benchmark expected comparison_policy in input.")

    def _require_action(self, actual: str, expected: str) -> None:
        if actual != expected:
            raise AssertionError(f"Expected action {expected!r}, got {actual!r}.")

    def _create_artifacts(self, action_name: str) -> ProviderArtifacts:
        invocation_dir = self.root_dir / self.case.case_id / action_name
        invocation_dir.mkdir(parents=True, exist_ok=True)
        sandbox_dir = invocation_dir / "workspace"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        return ProviderArtifacts(
            invocation_id=f"{self.case.case_id}-{action_name}",
            invocation_dir=invocation_dir,
            prompt_path=invocation_dir / "prompt.md",
            schema_path=invocation_dir / "schema.json",
            last_message_path=invocation_dir / "last-message.json",
            response_path=invocation_dir / "response.json",
            stdout_path=invocation_dir / "stdout.jsonl",
            stderr_path=invocation_dir / "stderr.txt",
            metadata_path=invocation_dir / "metadata.json",
            sandbox_dir=sandbox_dir,
            failure_path=invocation_dir / "failure.json",
        )


def _cases_of_kind(kind: EvaluatorBenchmarkKind) -> list[EvaluatorBenchmarkCase]:
    return [case for case in load_evaluator_benchmark_cases(_EVALUATOR_CASES_DIR) if case.kind is kind]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture_time():
    return _cases_of_kind(EvaluatorBenchmarkKind.RANKING)[0].nodes[0].to_node().created_at
