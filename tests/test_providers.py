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


class CodexProviderTests(unittest.TestCase):
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
    def test_run_action_uses_headless_json_mode_and_unwraps_response_text(self) -> None:
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
            self.assertIn("--output-format", command)
            self.assertIn("json", command)
            self.assertIn("--approval-mode", command)
            self.assertIn("plan", command)
            self.assertIn("--model", command)
            self.assertIn("gemini-2.5-pro", command)
            self.assertEqual(runner.calls[0]["cwd"], response.artifacts.sandbox_dir)
            self.assertEqual(last_message_text, json.dumps(_candidate_payload()))

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
    def __init__(self, *, outcome: CompletedRunnerResult | Exception) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        with self._lock:
            self.calls.append({"command": list(command), **kwargs})

        if isinstance(self.outcome, CompletedRunnerResult):
            if self.outcome.last_message is not None and "-o" in command:
                last_message_index = command.index("-o") + 1
                last_message_path = Path(command[last_message_index])
                last_message_path.write_text(self.outcome.last_message, encoding="utf-8")
            return subprocess.CompletedProcess(
                command,
                self.outcome.returncode,
                stdout=self.outcome.stdout,
                stderr=self.outcome.stderr,
            )

        raise self.outcome


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


def _comparison_payload(node_id: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "candidate": _candidate_payload(),
        "score": _evaluation_payload()["score"],
        "novelty_score": 0.63,
    }
