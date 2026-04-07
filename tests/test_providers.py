from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock
import unittest
from unittest.mock import patch

from argus.benchmarks import benchmark_comparison_assessment_schema
from argus.eval.evaluator import evaluation_assessment_schema, pairwise_ranking_assessment_schema
from argus.eval.novelty import novelty_assessment_schema
from argus.models import ActionType, Candidate, ProblemSpec
from argus.providers import (
    CodexProvider,
    GeminiProvider,
    OpenCodeProvider,
    ProviderInvocationError,
    StructuredOutputSchema,
)
from argus.search.contracts import hybrid_candidate_batch_schema, problem_frame_schema
from argus.search.research_contracts import final_decision_package_schema, search_space_plan_schema


class CodexProviderTests(unittest.TestCase):
    def test_problem_frame_schema_marks_candidate_implementation_shape_as_required_nullable(self) -> None:
        schema = problem_frame_schema().json_schema
        framing_candidate = schema["properties"]["framing_candidate"]
        self.assertIn("implementation_shape", framing_candidate["required"])
        self.assertEqual(
            framing_candidate["properties"]["implementation_shape"]["type"],
            ["string", "null"],
        )
        self.assertEqual(
            schema["properties"]["problem_spec"]["properties"]["context"],
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
                "required": [],
            },
        )

    def test_run_action_materializes_prompt_and_validates_structured_output(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_candidate_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                model="gpt-5",
                timeout_seconds=12.0,
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={"target_count": 3, "depth": 1},
                output_schema=_candidate_schema(),
            )

            self.assertEqual(response.provider_name, "codex")
            self.assertEqual(response.action_name, "generate_seed")
            self.assertEqual(response.payload, Candidate.from_dict(_candidate_payload()))
            self.assertEqual(response.raw_payload, _candidate_payload())

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
            self.assertIn("Action: generate_seed", prompt_text)
            self.assertIn('"request": "Find the best retention strategy."', prompt_text)
            self.assertIn('"target_count": 3', prompt_text)

            metadata = json.loads(response.artifacts.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "ok")
            self.assertEqual(metadata["provider_name"], "codex")
            self.assertEqual(metadata["action_name"], "generate_seed")
            self.assertEqual(metadata["model"], "gpt-5")

            self.assertTrue(response.artifacts.schema_path.is_file())
            self.assertTrue(response.artifacts.last_message_path.is_file())
            self.assertTrue(response.artifacts.response_path.is_file())
            self.assertTrue(response.artifacts.stdout_path.is_file())
            self.assertTrue(response.artifacts.stderr_path.is_file())
            self.assertFalse(response.artifacts.failure_path.exists())

            command = runner.calls[0]["command"]
            self.assertEqual(command[:2], ["codex", "exec"])
            self.assertIn("--model", command)
            self.assertIn("gpt-5", command)
            self.assertIn("--sandbox", command)
            self.assertIn("read-only", command)
            self.assertIn("--json", command)
            self.assertIn("--skip-git-repo-check", command)
            self.assertIn("--output-schema", command)
            self.assertIn("-o", command)

    def test_run_action_passes_reasoning_effort_override_to_codex(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_candidate_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                model="gpt-5.4",
                reasoning_effort="xhigh",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={"target_count": 1},
                output_schema=_candidate_schema(),
            )

            metadata = json.loads(response.artifacts.metadata_path.read_text(encoding="utf-8"))
            command = runner.calls[0]["command"]

        self.assertEqual(response.reasoning_effort, "xhigh")
        self.assertEqual(metadata["reasoning_effort"], "xhigh")
        self.assertIn("-c", command)
        self.assertIn('model_reasoning_effort="xhigh"', command)

    def test_run_action_serializes_nonzero_exit_failures(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=17,
                    stdout='{"event":"failed"}\n',
                    stderr="codex could not satisfy the request",
                    last_message=None,
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            with self.assertRaises(ProviderInvocationError) as captured:
                provider.run_action(
                    action_name="frame_problem",
                    problem_spec=_problem_spec(),
                    input_payload={},
                    output_schema=_candidate_schema(),
                )

            failure = captured.exception.failure
            failure_payload = json.loads(
                failure.artifacts.failure_path.read_text(encoding="utf-8")
            )
            metadata = json.loads(failure.artifacts.metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(failure.error_type, "process_exit")
        self.assertEqual(failure.exit_status, 17)
        self.assertIn("status 17", failure.message)
        self.assertEqual(failure_payload["error_type"], "process_exit")
        self.assertEqual(failure_payload["exit_status"], 17)
        self.assertEqual(metadata["status"], "failed")
        self.assertIn("could not satisfy the request", failure_payload["stderr_excerpt"])

    def test_run_action_serializes_schema_validation_failures(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps({"thesis": "Missing the rest of the schema."}),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            with self.assertRaises(ProviderInvocationError) as captured:
                provider.run_action(
                    action_name=ActionType.DEEPEN,
                    problem_spec=_problem_spec(),
                    input_payload={"node_id": "node-0004"},
                    output_schema=_candidate_schema(),
                )

            failure = captured.exception.failure
            response_payload = json.loads(
                failure.artifacts.response_path.read_text(encoding="utf-8")
            )

        self.assertEqual(failure.error_type, "schema_validation")
        self.assertEqual(response_payload, {"thesis": "Missing the rest of the schema."})
        self.assertIn("failed schema validation", failure.message)

    def test_run_action_ignores_accidental_top_level_schema_keywords(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(
                        {
                            **_novelty_payload(),
                            "additionalProperties": False,
                        }
                    ),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name="assess_novelty",
                problem_spec=_problem_spec(),
                input_payload={
                    "candidate": _candidate_payload(),
                    "archive_candidates": [
                        {
                            "node_id": "node-001",
                            "candidate": _candidate_payload(),
                        }
                    ],
                    "similarity_threshold": 0.8,
                },
                output_schema=novelty_assessment_schema(),
            )

            metadata = json.loads(response.artifacts.metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(response.payload, novelty_assessment_schema().validate(_novelty_payload()))
        self.assertFalse(response.payload.is_novel)
        self.assertEqual(response.raw_payload["additionalProperties"], False)
        self.assertEqual(metadata["stripped_schema_metadata_keys"], ["additionalProperties"])

    def test_run_action_still_rejects_non_schema_unexpected_keys(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(
                        {
                            **_novelty_payload(),
                            "bogus": "unexpected",
                        }
                    ),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            with self.assertRaises(ProviderInvocationError) as captured:
                provider.run_action(
                    action_name="assess_novelty",
                    problem_spec=_problem_spec(),
                    input_payload={
                        "candidate": _candidate_payload(),
                        "archive_candidates": [
                            {
                                "node_id": "node-001",
                                "candidate": _candidate_payload(),
                            }
                        ],
                        "similarity_threshold": 0.8,
                    },
                    output_schema=novelty_assessment_schema(),
                )

        failure = captured.exception.failure
        self.assertEqual(failure.error_type, "schema_validation")
        self.assertIn("unexpected keys: bogus", failure.message)

    def test_run_action_serializes_timeout_failures(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=subprocess.TimeoutExpired(
                    cmd=["codex", "exec"],
                    timeout=1.5,
                    output='{"event":"thinking"}\n',
                    stderr="deadline exceeded",
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                timeout_seconds=1.5,
                runner=runner,
            )

            with self.assertRaises(ProviderInvocationError) as captured:
                provider.run_action(
                    action_name=ActionType.MUTATE,
                    problem_spec=_problem_spec(),
                    input_payload={"node_id": "node-0005"},
                    output_schema=_candidate_schema(),
                )

            failure = captured.exception.failure
            metadata = json.loads(failure.artifacts.metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(failure.error_type, "timeout")
        self.assertIsNone(failure.exit_status)
        self.assertEqual(metadata["status"], "failed")
        self.assertIn("timed out", failure.message)
        self.assertIn("deadline exceeded", metadata["stderr_excerpt"])

    def test_run_action_materializes_action_specific_evaluation_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_evaluation_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name="evaluate_candidate",
                problem_spec=_problem_spec(),
                input_payload={
                    "candidate": _candidate_payload(),
                    "novelty_score": 0.71,
                    "reusable_learning_notes": [
                        {
                            "note_id": "learning-abc123",
                            "note_type": "winning_pattern",
                            "text": "Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
                            "evidence_sources": ["outcome_feedback"],
                            "observation_count": 2,
                            "source_run_ids": ["run-a", "run-b"],
                            "problem_statements": ["Find the best retention strategy."],
                        }
                    ],
                },
                output_schema=evaluation_assessment_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: candidate evaluator for Argus.", prompt_text)
        self.assertIn("Hard-constraint gate: set score.hard_constraint_pass=false", prompt_text)
        self.assertIn("Anti-style rule: do not reward polish, buzzwords, generic optimism", prompt_text)
        self.assertIn("Reusable priors: when reusable_learning_notes are present", prompt_text)
        self.assertIn("outcome_feedback", prompt_text)

    def test_run_action_materializes_action_specific_novelty_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_novelty_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name="assess_novelty",
                problem_spec=_problem_spec(),
                input_payload={
                    "candidate": _candidate_payload(),
                    "archive_candidates": [
                        {
                            "node_id": "node-001",
                            "candidate": _candidate_payload(),
                        }
                    ],
                    "similarity_threshold": 0.8,
                },
                output_schema=novelty_assessment_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: semantic novelty judge for Argus archive admission.", prompt_text)
        self.assertIn("Near-duplicate rule: mark is_novel=false", prompt_text)
        self.assertIn(
            "Shared-vocabulary rule: do not reject a candidate just because it uses similar domain terms.",
            prompt_text,
        )

    def test_run_action_materializes_action_specific_pairwise_ranking_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_pairwise_ranking_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.RANK,
                problem_spec=_problem_spec(),
                input_payload={
                    "objective": {
                        "name": "conservative_option",
                        "description": "Choose the safer, more implementation-ready option.",
                    },
                    "left": _comparison_payload("node-left"),
                    "right": _comparison_payload("node-right"),
                },
                output_schema=pairwise_ranking_assessment_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: pairwise ranking judge for Argus finalist selection.", prompt_text)
        self.assertIn("There are no ties.", prompt_text)
        self.assertIn("Objective-specific focus for conservative_option:", prompt_text)
        self.assertIn(
            "Prefer operational clarity, tractability, plausibility, robustness, and confidence over raw upside.",
            prompt_text,
        )

    def test_run_action_materializes_action_specific_benchmark_comparison_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_benchmark_comparison_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name="judge_benchmark_modes",
                problem_spec=_problem_spec(),
                input_payload={
                    "benchmark_case": {
                        "case_id": "product-strategy-retention",
                        "title": "Fixture benchmark case",
                        "family": "product_strategy",
                        "budget": 9,
                        "evaluation_notes": ["Prefer durable workflow habits over decorative engagement loops."],
                        "expected_qualities": ["Produce differentiated bets with explicit tradeoffs."],
                        "tags": ["fixture"],
                    },
                    "mode_outputs": [
                        {
                            "runtime_mode": "adaptive",
                            "summary_markdown": "Adaptive summary",
                            "final_recommendation": _final_recommendation_payload(),
                            "selected_theses": {
                                "best_bet": "Adaptive best bet",
                                "conservative": "Adaptive conservative",
                                "high_upside": "Adaptive upside",
                            },
                        },
                        {
                            "runtime_mode": "research",
                            "summary_markdown": "Research summary",
                            "final_recommendation": _final_recommendation_payload(),
                            "selected_theses": {
                                "best_bet": "Research best bet",
                                "conservative": "Research conservative",
                                "high_upside": "Research upside",
                            },
                            "research_final_decision": {
                                "summary": "Typed final decision doc.",
                            },
                        },
                    ],
                },
                output_schema=benchmark_comparison_assessment_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: benchmark comparison judge for Argus runtime modes.", prompt_text)
        self.assertIn("Primary question: which runtime output would a serious team act on next", prompt_text)
        self.assertIn("Anti-style rule: do not reward longer prose", prompt_text)
        self.assertIn("Comparison scope: evaluate all 2 runtime modes", prompt_text)
        self.assertEqual(response.payload.winner_runtime_mode.value, "research")

    def test_run_action_materializes_action_specific_migration_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_candidate_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.MIGRATE,
                problem_spec=_problem_spec(),
                input_payload={
                    "source_island": {"island_id": "balanced", "generation_focus": "Favor well-rounded ideas."},
                    "destination_island": {
                        "island_id": "upside",
                        "generation_focus": "Favor high-leverage opportunities.",
                    },
                    "source_node_id": "node-0006",
                    "source_candidate": _candidate_payload(),
                    "migration_policy": {"goal": "Adapt the source insight to the destination island."},
                },
                output_schema=_candidate_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: cross-island migration worker for Argus.", prompt_text)
        self.assertIn(
            "carry the strongest causal insight from the source candidate into the destination island's optimization bias",
            prompt_text,
        )
        self.assertIn("Do not paraphrase the source candidate.", prompt_text)

    def test_run_action_materializes_action_specific_generation_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_candidate_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={
                    "target_count": 3,
                    "framing_candidate": _candidate_payload(),
                    "generation_policy": {
                        "diversity_requirement": "Return materially distinct strategic directions.",
                        "quality_requirement": "Prefer executable mechanisms with explicit tradeoffs.",
                        "island_focus": "Favor well-rounded mechanisms that can win on substance.",
                    },
                },
                output_schema=_candidate_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: seed generator for Argus.", prompt_text)
        self.assertIn("Diversity rule: generate meaningfully different strategic directions", prompt_text)
        self.assertIn("Target count: return exactly 3 seed candidates.", prompt_text)
        self.assertIn("Island-specific focus: Favor well-rounded mechanisms", prompt_text)

    def test_run_action_materializes_action_specific_stress_test_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(
                        {
                            "hidden_dependencies": ["Teams must already trust the archive."],
                            "kill_shots": ["The ritual may not justify the setup cost."],
                            "sharp_edges": ["Rollout could fail for casual teams."],
                            "summary": "The candidate survives only if the weekly ritual already exists.",
                        }
                    ),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.STRESS_TEST,
                problem_spec=_problem_spec(),
                input_payload={
                    "candidate": _candidate_payload(),
                    "stress_test_policy": {
                        "focus": [
                            "hidden dependencies",
                            "kill shots",
                            "operational sharp edges",
                        ]
                    },
                },
                output_schema=StructuredOutputSchema(
                    name="critique",
                    json_schema={
                        "type": "object",
                        "required": ["hidden_dependencies", "kill_shots", "sharp_edges", "summary"],
                        "properties": {
                            "hidden_dependencies": {"type": "array", "items": {"type": "string"}},
                            "kill_shots": {"type": "array", "items": {"type": "string"}},
                            "sharp_edges": {"type": "array", "items": {"type": "string"}},
                            "summary": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    validator=lambda payload: payload,
                ),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: adversarial stress tester for Argus.", prompt_text)
        self.assertIn("Your job is to attack the candidate, not to help it.", prompt_text)
        self.assertIn("Ruthlessness rule: prefer concrete kill shots over polite generic critique.", prompt_text)
        self.assertIn("Stress-test focus: hidden dependencies; kill shots; operational sharp edges.", prompt_text)

    def test_run_action_materializes_action_specific_refinement_prompts(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=[
                    CompletedRunnerResult(
                        returncode=0,
                        stdout='{"event":"completed"}\n',
                        stderr="",
                        last_message=json.dumps(_candidate_payload()),
                    ),
                    CompletedRunnerResult(
                        returncode=0,
                        stdout='{"event":"completed"}\n',
                        stderr="",
                        last_message=json.dumps(
                            {
                                "candidates": [_candidate_payload()],
                                "batch_summary": "Mutated the candidate without changing the core mechanism.",
                            }
                        ),
                    ),
                    CompletedRunnerResult(
                        returncode=0,
                        stdout='{"event":"completed"}\n',
                        stderr="",
                        last_message=json.dumps(_hybrid_candidate_batch_payload()),
                    ),
                ]
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            deepen_response = provider.run_action(
                action_name=ActionType.DEEPEN,
                problem_spec=_problem_spec(),
                input_payload={
                    "candidate": _candidate_payload(),
                    "deepen_policy": {
                        "goal": "Increase specificity and execution readiness without collapsing distinctiveness."
                    },
                },
                output_schema=_candidate_schema(),
            )
            mutate_response = provider.run_action(
                action_name=ActionType.MUTATE,
                problem_spec=_problem_spec(),
                input_payload={
                    "candidate": _candidate_payload(),
                    "mutation_policy": {
                        "goal": "Address the sharpest weakness while preserving the core mechanism."
                    },
                },
                output_schema=StructuredOutputSchema(
                    name="candidate_batch",
                    json_schema={
                        "type": "object",
                        "required": ["candidates", "batch_summary"],
                        "properties": {
                            "candidates": {"type": "array", "items": _candidate_schema().json_schema},
                            "batch_summary": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    validator=lambda payload: payload,
                ),
            )
            combine_response = provider.run_action(
                action_name=ActionType.COMBINE,
                problem_spec=_problem_spec(),
                input_payload={
                    "primary_candidate": _candidate_payload(),
                    "secondary_candidate": _candidate_payload(),
                    "combine_policy": {
                        "goal": "Fuse compatible strengths only if the combined direction remains coherent and distinct."
                    },
                },
                output_schema=hybrid_candidate_batch_schema(),
            )
            deepen_prompt = deepen_response.artifacts.prompt_path.read_text(encoding="utf-8")
            mutate_prompt = mutate_response.artifacts.prompt_path.read_text(encoding="utf-8")
            combine_prompt = combine_response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: deepening worker for Argus.", deepen_prompt)
        self.assertIn("Deepening goal: Increase specificity and execution readiness", deepen_prompt)
        self.assertIn("Role: mutation worker for Argus.", mutate_prompt)
        self.assertIn("Mutation goal: Address the sharpest weakness", mutate_prompt)
        self.assertIn("Role: hybrid synthesis worker for Argus adaptive search.", combine_prompt)
        self.assertIn("Gate rule: every hybrid decision must explicitly name the repaired_failure_mode", combine_prompt)

    def test_run_action_materializes_action_specific_learning_compression_prompt(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(
                        {
                            "notes": [
                                {
                                    "note_type": "winning_pattern",
                                    "text": "Workflow-native artifacts compound into repeated usage.",
                                    "source_node_ids": ["node-0002"],
                                }
                            ],
                            "summary": "The run rewarded workflow-native review loops.",
                        }
                    ),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.COMPRESS_LEARNING,
                problem_spec=_problem_spec(),
                input_payload={
                    "archived_nodes": [],
                    "pruned_nodes": [],
                    "max_notes": 4,
                    "compression_policy": {
                        "goal": "Extract reusable patterns, failure modes, and constraints from the current search state."
                    },
                },
                output_schema=StructuredOutputSchema(
                    name="learning_compression",
                    json_schema={
                        "type": "object",
                        "required": ["notes", "summary"],
                        "properties": {
                            "notes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["note_type", "text", "source_node_ids"],
                                    "properties": {
                                        "note_type": {"type": "string"},
                                        "text": {"type": "string"},
                                        "source_node_ids": {"type": "array", "items": {"type": "string"}},
                                    },
                                    "additionalProperties": False,
                                },
                            },
                            "summary": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    validator=lambda payload: payload,
                ),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("Role: learning compression worker for Argus.", prompt_text)
        self.assertIn("Note budget: return at most 4 compressed learning notes.", prompt_text)
        self.assertIn("Compression goal: Extract reusable patterns, failure modes, and constraints", prompt_text)

    def test_run_action_materializes_action_specific_research_prompts(self) -> None:
        with TemporaryDirectory() as directory:
            frame_runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_search_space_plan_payload()),
                )
            )
            decision_runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_final_decision_package_payload()),
                )
            )
            frame_provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations" / "frame",
                runner=frame_runner,
            )
            decision_provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations" / "decision",
                runner=decision_runner,
            )

            frame_response = frame_provider.run_action(
                action_name="frame_search_space",
                problem_spec=_problem_spec(),
                input_payload={"request": _problem_spec().request, "budget": 7},
                output_schema=search_space_plan_schema(),
            )
            decision_response = decision_provider.run_action(
                action_name="write_final_decision",
                problem_spec=_problem_spec(),
                input_payload={
                    "frame_id": "frame-001",
                    "proposals": [
                        {
                            "proposal_id": "proposal-ledger",
                            "cell_id": "cell-ledger",
                            "title": "Coverage-led runtime",
                            "summary": "Use an explicit coverage ledger.",
                            "candidate": _candidate_payload(),
                            "seed_rationale": "Closes the main product gap.",
                            "open_questions": ["Latency?"],
                            "evidence": ["Spec-aligned."],
                            "parent_node_ids": ["node-0002"],
                        }
                    ],
                },
                output_schema=final_decision_package_schema(),
            )

            frame_prompt = frame_response.artifacts.prompt_path.read_text(encoding="utf-8")
            decision_prompt = decision_response.artifacts.prompt_path.read_text(encoding="utf-8")

        self.assertIn("Role: search-space framer for Argus research mode.", frame_prompt)
        self.assertIn("Ledger rule: return an initial coverage_ledger", frame_prompt)
        self.assertIn("Role: final decision author for Argus research mode.", decision_prompt)
        self.assertIn("Comparison rule: produce a comparison_matrix", decision_prompt)
        self.assertIn("decision_summary_markdown", decision_prompt)
        self.assertIn("decision_report_markdown", decision_prompt)

    def test_run_action_pairwise_prompt_mentions_outcome_feedback_priors(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_pairwise_ranking_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.RANK,
                problem_spec=_problem_spec(),
                input_payload={
                    "objective": {
                        "name": "best_overall",
                        "description": "Choose the strongest overall recommendation.",
                    },
                    "left": _comparison_payload("node-left"),
                    "right": _comparison_payload("node-right"),
                    "reusable_learning_notes": [
                        {
                            "note_id": "learning-outcome-1",
                            "note_type": "failure_pattern",
                            "text": "Setup-heavy plans fail when the first audit artifact arrives too late.",
                            "evidence_sources": ["outcome_feedback"],
                            "observation_count": 1,
                            "source_run_ids": ["run-outcome"],
                            "problem_statements": ["Find the best retention strategy."],
                        }
                    ],
                },
                output_schema=pairwise_ranking_assessment_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
        self.assertIn("outcome_feedback", prompt_text)

    def test_run_action_allocates_unique_artifact_dirs_under_concurrency(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout='{"event":"completed"}\n',
                    stderr="",
                    last_message=json.dumps(_candidate_payload()),
                )
            )
            provider = CodexProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            class FixedDatetime(datetime):
                @classmethod
                def now(cls, tz=None) -> datetime:
                    fixed = datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
                    return fixed if tz is None else fixed.astimezone(tz)

            with patch("argus.providers.cli_base.datetime", FixedDatetime):
                with ThreadPoolExecutor(max_workers=3) as executor:
                    responses = list(
                        executor.map(
                            lambda _: provider.run_action(
                                action_name=ActionType.GENERATE_SEED,
                                problem_spec=_problem_spec(),
                                input_payload={"target_count": 1},
                                output_schema=_candidate_schema(),
                            ),
                            range(3),
                        )
                    )

        invocation_ids = sorted(response.artifacts.invocation_id for response in responses)
        expected_base = "20260306T120000000000Z-generate-seed"
        self.assertEqual(
            invocation_ids,
            [
                expected_base,
                f"{expected_base}-01",
                f"{expected_base}-02",
            ],
        )
        self.assertEqual(len(runner.calls), 3)


class GeminiProviderTests(unittest.TestCase):
    def test_run_action_uses_headless_json_mode_with_stdin_prompt_and_unwraps_response_text(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "session_id": "gemini-session",
                            "response": json.dumps(_candidate_payload()),
                            "stats": {"total_tokens": 42},
                        }
                    ),
                    stderr="",
                    last_message=None,
                )
            )
            provider = GeminiProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                model="gemini-2.5-pro",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={"target_count": 2},
                output_schema=_candidate_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")
            last_message_text = response.artifacts.last_message_path.read_text(encoding="utf-8")

            self.assertEqual(response.provider_name, "gemini")
            self.assertEqual(response.payload, Candidate.from_dict(_candidate_payload()))
            self.assertIn("# Argus Gemini Worker", prompt_text)

            command = runner.calls[0]["command"]
            self.assertEqual(command[0], "gemini")
            self.assertIn("--prompt", command)
            self.assertEqual(command[command.index("--prompt") + 1], "")
            self.assertIn("--output-format", command)
            self.assertIn("json", command)
            self.assertNotIn("--approval-mode", command)
            self.assertIn("--model", command)
            self.assertIn("gemini-2.5-pro", command)
            self.assertEqual(runner.calls[0]["cwd"], response.artifacts.sandbox_dir)
            self.assertEqual(runner.calls[0]["input"], prompt_text)
            self.assertNotIn(prompt_text, command)
            self.assertEqual(last_message_text, json.dumps(_candidate_payload()))

    def test_run_action_unwraps_markdown_fenced_response_text(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "session_id": "gemini-session",
                            "response": f"```json\n{json.dumps(_candidate_payload(), indent=2)}\n```",
                            "stats": {"total_tokens": 42},
                        }
                    ),
                    stderr="",
                    last_message=None,
                )
            )
            provider = GeminiProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={"target_count": 2},
                output_schema=_candidate_schema(),
            )

            self.assertEqual(response.provider_name, "gemini")
            self.assertEqual(response.payload, Candidate.from_dict(_candidate_payload()))

    def test_run_action_retries_once_after_invalid_json_response_text(self) -> None:
        payload = _candidate_payload()
        payload_text = json.dumps(payload, indent=2)
        trailing_comma_payload = payload_text[:-2] + ",\n}"
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=[
                    CompletedRunnerResult(
                        returncode=0,
                        stdout=json.dumps(
                            {
                                "session_id": "gemini-session",
                                "response": trailing_comma_payload,
                                "stats": {"total_tokens": 42},
                            }
                        ),
                        stderr="",
                        last_message=None,
                    ),
                    CompletedRunnerResult(
                        returncode=0,
                        stdout=json.dumps(
                            {
                                "session_id": "gemini-session",
                                "response": json.dumps(_candidate_payload()),
                                "stats": {"total_tokens": 42},
                            }
                        ),
                        stderr="",
                        last_message=None,
                    ),
                ]
            )
            provider = GeminiProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={"target_count": 2},
                output_schema=_candidate_schema(),
            )

            self.assertEqual(response.provider_name, "gemini")
            self.assertEqual(response.payload, Candidate.from_dict(_candidate_payload()))
            self.assertEqual(len(runner.calls), 2)

    def test_run_action_fails_when_json_envelope_has_no_response_field(self) -> None:
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout=json.dumps({"session_id": "gemini-session", "stats": {"total_tokens": 9}}),
                    stderr="",
                    last_message=None,
                )
            )
            provider = GeminiProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            with self.assertRaises(ProviderInvocationError) as captured:
                provider.run_action(
                    action_name=ActionType.GENERATE_SEED,
                    problem_spec=_problem_spec(),
                    input_payload={"target_count": 2},
                    output_schema=_candidate_schema(),
                )

        failure = captured.exception.failure
        self.assertEqual(failure.error_type, "missing_output")
        self.assertIn("response", failure.message)


class OpenCodeProviderTests(unittest.TestCase):
    def test_run_action_reassembles_json_from_message_part_delta_events(self) -> None:
        candidate_json = json.dumps(_candidate_payload())
        midpoint = len(candidate_json) // 2
        stdout = "\n".join(
            json.dumps(event)
            for event in [
                {
                    "event": "message.part.delta",
                    "data": {
                        "sessionID": "session-1",
                        "messageID": "message-1",
                        "partID": "part-1",
                        "field": "text",
                        "delta": candidate_json[:midpoint],
                    },
                },
                {
                    "event": "message.part.delta",
                    "data": {
                        "sessionID": "session-1",
                        "messageID": "message-1",
                        "partID": "part-1",
                        "field": "text",
                        "delta": candidate_json[midpoint:],
                    },
                },
            ]
        )
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout=stdout,
                    stderr="",
                    last_message=None,
                )
            )
            provider = OpenCodeProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                model="openai/gpt-5",
                runner=runner,
            )

            response = provider.run_action(
                action_name=ActionType.GENERATE_SEED,
                problem_spec=_problem_spec(),
                input_payload={"target_count": 2},
                output_schema=_candidate_schema(),
            )

            prompt_text = response.artifacts.prompt_path.read_text(encoding="utf-8")

            self.assertEqual(response.provider_name, "opencode")
            self.assertEqual(response.payload, Candidate.from_dict(_candidate_payload()))
            self.assertIn("# Argus OpenCode Worker", prompt_text)

            command = runner.calls[0]["command"]
            self.assertEqual(command[:2], ["opencode", "run"])
            self.assertIn("--format", command)
            self.assertIn("json", command)
            self.assertIn("--dir", command)
            self.assertIn("--model", command)
            self.assertIn("openai/gpt-5", command)
            self.assertEqual(command[-1], prompt_text)

    def test_run_action_fails_when_event_stream_has_no_assistant_text(self) -> None:
        stdout = json.dumps(
            {
                "event": "message.part.updated",
                "data": {
                    "part": {
                        "id": "part-1",
                        "type": "tool",
                        "text": "tool output",
                    }
                },
            }
        )
        with TemporaryDirectory() as directory:
            runner = FakeCliRunner(
                outcome=CompletedRunnerResult(
                    returncode=0,
                    stdout=stdout,
                    stderr="",
                    last_message=None,
                )
            )
            provider = OpenCodeProvider(
                artifacts_root=Path(directory) / "artifacts" / "provider_invocations",
                runner=runner,
            )

            with self.assertRaises(ProviderInvocationError) as captured:
                provider.run_action(
                    action_name=ActionType.GENERATE_SEED,
                    problem_spec=_problem_spec(),
                    input_payload={"target_count": 2},
                    output_schema=_candidate_schema(),
                )

        failure = captured.exception.failure
        self.assertEqual(failure.error_type, "missing_output")
        self.assertIn("assistant text response", failure.message)


class FakeCliRunner:
    def __init__(
        self,
        *,
        outcome: CompletedRunnerResult | Exception | list[CompletedRunnerResult | Exception],
    ) -> None:
        if isinstance(outcome, list):
            if not outcome:
                raise ValueError("outcome list must not be empty.")
            self.outcomes: list[CompletedRunnerResult | Exception] = list(outcome)
        else:
            self.outcomes = [outcome]
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        with self._lock:
            self.calls.append({"command": list(command), **kwargs})
            outcome = (
                self.outcomes.pop(0)
                if len(self.outcomes) > 1
                else self.outcomes[0]
            )

        if isinstance(outcome, CompletedRunnerResult):
            if outcome.last_message is not None and "-o" in command:
                last_message_index = command.index("-o") + 1
                last_message_path = Path(command[last_message_index])
                last_message_path.write_text(outcome.last_message, encoding="utf-8")
            return subprocess.CompletedProcess(
                command,
                outcome.returncode,
                stdout=outcome.stdout,
                stderr=outcome.stderr,
            )

        raise outcome


class CompletedRunnerResult:
    def __init__(
        self,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        last_message: str | None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.last_message = last_message


def _problem_spec() -> ProblemSpec:
    return ProblemSpec(
        request="Find the best retention strategy.",
        constraints=["Stay self-serve.", "Keep the system auditable."],
        success_criteria=["Increase activation.", "Make tradeoffs explicit."],
        context={"team": "growth"},
    )


def _candidate_schema() -> StructuredOutputSchema[Candidate]:
    return StructuredOutputSchema(
        name="candidate",
        json_schema={
            "type": "object",
            "required": [
                "thesis",
                "mechanism",
                "assumptions",
                "strengths",
                "failure_modes",
                "unknowns",
                "evidence",
            ],
            "properties": {
                "thesis": {"type": "string"},
                "mechanism": {"type": "string"},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "failure_modes": {"type": "array", "items": {"type": "string"}},
                "unknowns": {"type": "array", "items": {"type": "string"}},
                "implementation_shape": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        validator=Candidate.from_dict,
    )


def _candidate_payload() -> dict[str, object]:
    return {
        "thesis": "Embed the product into repeated operating rituals.",
        "mechanism": "Tie user success to a weekly workflow checkpoint with clear outputs.",
        "assumptions": ["Users will tolerate a little setup work for better outcomes."],
        "strengths": ["Creates a recurring reason to return."],
        "failure_modes": ["May add onboarding friction for casual users."],
        "unknowns": ["How much configuration the target segment will accept."],
        "implementation_shape": "Persist the workflow state and score outcomes explicitly.",
        "evidence": ["Argus should favor evaluator-first, replayable systems."],
    }


def _hybrid_candidate_batch_payload() -> dict[str, object]:
    return {
        "decisions": [
            {
                "hybrid_name": "Workflow archive with delayed benchmark layer",
                "seam_hypothesis": (
                    "The workflow archive establishes trust and recurring value before the benchmark layer turns on."
                ),
                "repaired_failure_mode": "The benchmark idea fails when trust and proprietary value are too weak at launch.",
                "complementary_strengths": [
                    "Archive path creates durable internal value.",
                    "Benchmark path creates upside after trust exists.",
                ],
                "complexity_tax": "Requires sequencing two modes and deferring the benchmark layer.",
                "expected_upside": "Preserves the moat while keeping a credible expansion path.",
                "open_questions": [
                    "What trust threshold is high enough before any benchmark sharing turns on?"
                ],
                "verdict": "pursue",
                "summary": "Pursue the hybrid because sequencing repairs the core weakness without bloating the initial product.",
                "candidate": _candidate_payload(),
            }
        ],
        "batch_summary": "Evaluated one hybrid seam and approved the strongest version.",
    }


def _evaluation_payload() -> dict[str, object]:
    return {
        "score": {
            "hard_constraint_pass": True,
            "hard_constraint_reasons": [],
            "distinctiveness": 0.73,
            "usefulness": 0.86,
            "specificity": 0.78,
            "plausibility": 0.81,
            "implementation_tractability": 0.79,
            "upside": 0.71,
            "adversarial_robustness": 0.68,
            "evidence_quality": 0.66,
            "total_score": 6.02,
            "confidence_estimate": 0.77,
        },
        "summary": "The candidate is strong because it directly supports repeatable retention loops.",
        "strengths": ["Strong connection between workflow habit and product value."],
        "weaknesses": ["Could still add some onboarding friction."],
        "open_questions": ["How much setup effort will the target segment tolerate?"],
    }


def _novelty_payload() -> dict[str, object]:
    return {
        "novelty_score": 0.22,
        "max_similarity": 0.84,
        "nearest_neighbor_id": "node-001",
        "similarity_threshold": 0.8,
        "is_novel": False,
        "summary": "The candidate is a near-duplicate of the archived workflow ritual idea.",
        "duplicate_signals": ["Same retention mechanism.", "Same rollout shape."],
    }


def _pairwise_ranking_payload() -> dict[str, object]:
    return {
        "winner": "left",
        "summary": "The left option is safer to ship without giving up the core value loop.",
        "decisive_advantages": ["Cleaner implementation path."],
        "decisive_risks": ["May leave some upside on the table."],
        "confidence": 0.81,
    }


def _benchmark_comparison_payload() -> dict[str, object]:
    return {
        "winner_runtime_mode": "research",
        "runner_up_runtime_mode": "adaptive",
        "summary": "The research runtime produces the most decision-grade benchmark artifact bundle.",
        "confidence": 0.84,
        "decisive_reasons": [
            "It preserves clearer runner-up logic and explicit reversal conditions.",
            "Its next experiment is more discriminating and actionable.",
        ],
        "watchouts": ["The richer artifact set still has a latency cost."],
        "mode_judgments": [
            {
                "runtime_mode": "adaptive",
                "decision_quality": 0.74,
                "actionability": 0.8,
                "tradeoff_clarity": 0.7,
                "risk_quality": 0.72,
                "experiment_quality": 0.78,
                "overall_score": 0.76,
                "strengths": ["Good rollout clarity."],
                "weaknesses": ["Less explicit runner-up logic."],
                "evidence": ["Summary markdown includes a viable first experiment."],
            },
            {
                "runtime_mode": "research",
                "decision_quality": 0.92,
                "actionability": 0.89,
                "tradeoff_clarity": 0.94,
                "risk_quality": 0.9,
                "experiment_quality": 0.91,
                "overall_score": 0.92,
                "strengths": ["Best decision package."],
                "weaknesses": ["Costs more authoring time."],
                "evidence": ["Final decision doc names the runner-up and reversal conditions."],
            },
        ],
    }


def _final_recommendation_payload() -> dict[str, object]:
    return {
        "best_bet_node_id": "node-001",
        "conservative_node_id": "node-002",
        "high_upside_node_id": "node-003",
        "rejected_but_insightful_ids": ["node-004"],
        "summary_markdown": "Benchmark-ready summary.",
        "next_experiments": ["Run the first discriminating spike."],
        "assumptions": ["Operators value auditable outputs."],
        "failure_modes": ["The artifact package may still be too heavy."],
        "reversal_conditions": ["If the decision package is not materially more actionable."],
    }


def _comparison_payload(node_id: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "candidate": _candidate_payload(),
        "score": _evaluation_payload()["score"],
        "novelty_score": 0.63,
    }


def _search_space_plan_payload() -> dict[str, object]:
    return {
        "search_space_frame": {
            "frame_id": "frame-001",
            "problem_statement": "Choose the next Argus research runtime.",
            "target_decision": "Pick the default runtime to ship.",
            "hard_gates": ["Must stay deterministic."],
            "soft_criteria": ["Decision quality", "Latency"],
            "baseline_options": ["Keep the adaptive runtime."],
            "axes": [
                {
                    "axis_id": "coverage",
                    "label": "Coverage",
                    "description": "Coverage planning mode.",
                    "options": ["implicit frontier", "explicit ledger"],
                }
            ],
            "coverage_plan": ["Seed each material family once."],
            "notes": ["Keep the adaptive path as a benchmark control."],
        },
        "coverage_ledger": {
            "ledger_id": "ledger-001",
            "frame_id": "frame-001",
            "cells": [
                {
                    "cell_id": "cell-ledger",
                    "label": "Explicit ledger",
                    "axis_assignments": {"coverage": "explicit ledger"},
                    "hypothesis": "Higher authoring cost for stronger decisions.",
                    "coverage_status": "unexplored",
                    "uncertainty": 0.55,
                    "hard_gate_risk": 0.24,
                    "evidence_strength": 0.42,
                    "incumbent_proposal_ids": [],
                    "notes": [],
                }
            ],
            "coverage_summary": "The explicit-ledger path is worth seeding.",
            "next_questions": ["Can it stay within the latency budget?"],
            "updated_at": "2026-03-08T18:30:00Z",
        },
    }


def _final_decision_package_payload() -> dict[str, object]:
    return {
        "comparison_matrix": {
            "matrix_id": "matrix-001",
            "frame_id": "frame-001",
            "criteria": ["decision_quality", "latency"],
            "rows": [
                {
                    "proposal_id": "proposal-ledger",
                    "criterion_scores": {
                        "decision_quality": 0.9,
                        "latency": 0.58,
                    },
                    "advantages": ["Best decision package."],
                    "liabilities": ["More authoring work."],
                    "takeaway": "Best default if latency stays bounded.",
                }
            ],
            "summary": "The coverage-led path wins on decision quality.",
        },
        "final_decision_doc": {
            "decision_id": "decision-001",
            "frame_id": "frame-001",
            "selected_proposal_id": "proposal-ledger",
            "summary": "Ship the coverage-led runtime.",
            "decision_rule": "Prefer the option that most improves decision quality without breaking determinism.",
            "assumptions": ["Artifact persistence stays inspectable."],
            "top_risks": ["Authoring latency could grow too high."],
            "mitigations": ["Keep provider dispatch bounded and deterministic."],
            "first_spike": ["Persist the research bundle under each run."],
            "kill_criteria": ["If the richer bundle breaks replay or verification."],
            "next_experiments": ["Benchmark the research runtime."],
            "reversal_conditions": ["If decision quality does not improve materially."],
            "rejected_proposal_ids": [],
        },
        "decision_summary_markdown": (
            "# Argus Recommendation\n\n"
            "Ship the coverage-led runtime.\n"
        ),
        "decision_report_markdown": (
            "# Final Decision Memo\n\n"
            "The coverage-led runtime should ship next.\n"
        ),
    }
