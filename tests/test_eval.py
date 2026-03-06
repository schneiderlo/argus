from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from argus.errors import ArgusValidationError
from argus.eval import (
    AgenticEvaluator,
    AgenticNoveltyFilter,
    EvaluationAssessment,
    NoveltyAssessment,
    PairwiseRankingAssessment,
    rank_nodes,
)
from argus.models import (
    ActionType,
    Candidate,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ScoreVector,
)
from argus.providers import ProviderArtifacts, ProviderResponse

_DEFAULT_SCORE = object()


class AgenticEvaluatorTests(unittest.TestCase):
    def test_agentic_evaluator_delegates_to_provider_with_structured_rubric(self) -> None:
        assessment = EvaluationAssessment(
            score=_strong_score(),
            summary="This candidate directly addresses the brief.",
            strengths=["Strong fit to the local-first workflow requirement."],
            weaknesses=["Could still feel heavy during setup."],
            open_questions=["How much setup will self-serve teams tolerate?"],
        )
        with TemporaryDirectory() as directory:
            provider = FakeProvider(Path(directory), {"evaluate_candidate": assessment})
            evaluator = AgenticEvaluator(provider=provider)

            result = evaluator.evaluate(
                _problem_spec(),
                _strong_candidate(),
                novelty_score=0.72,
            )

        self.assertEqual(result, assessment)
        self.assertEqual(provider.calls[0]["action_name"], "evaluate_candidate")
        self.assertEqual(provider.calls[0]["input_payload"]["novelty_score"], 0.72)
        self.assertIn("rubric", provider.calls[0]["input_payload"])

    def test_rank_nodes_orders_by_score_then_confidence(self) -> None:
        ranked = rank_nodes(
            [
                _node("node-001", total_score=4.5, confidence=0.60, novelty_score=0.6),
                _node("node-002", total_score=5.1, confidence=0.74, novelty_score=0.4),
                _node("node-003", total_score=5.1, confidence=0.68, novelty_score=0.8),
            ]
        )

        self.assertEqual([node.node_id for node in ranked], ["node-002", "node-003", "node-001"])

    def test_rank_nodes_requires_scores(self) -> None:
        with self.assertRaises(ArgusValidationError):
            rank_nodes([_node("node-999", score=None, novelty_score=0.6)])

    def test_agentic_evaluator_compares_nodes_with_provider_backed_pairwise_rank(self) -> None:
        assessment = PairwiseRankingAssessment(
            winner="right",
            summary="The right candidate is more execution-ready without losing the core upside.",
            decisive_advantages=["Cleaner rollout path."],
            decisive_risks=["Could leave some upside on the table."],
            confidence=0.79,
        )
        with TemporaryDirectory() as directory:
            provider = FakeProvider(Path(directory), {"rank": assessment})
            evaluator = AgenticEvaluator(provider=provider)

            result = evaluator.compare_nodes(
                _problem_spec(),
                _node("node-001", total_score=6.2, confidence=0.8, novelty_score=0.61),
                _node("node-002", total_score=6.1, confidence=0.84, novelty_score=0.55),
                objective="best_overall",
                objective_description="Choose the stronger overall recommendation.",
            )

        self.assertEqual(result, assessment)
        self.assertEqual(provider.calls[0]["action_name"], "rank")
        self.assertEqual(provider.calls[0]["input_payload"]["objective"]["name"], "best_overall")
        self.assertEqual(provider.calls[0]["input_payload"]["left"]["node_id"], "node-001")
        self.assertEqual(provider.calls[0]["input_payload"]["right"]["node_id"], "node-002")


class AgenticNoveltyFilterTests(unittest.TestCase):
    def test_agentic_novelty_filter_short_circuits_for_empty_archive(self) -> None:
        with TemporaryDirectory() as directory:
            provider = FakeProvider(Path(directory), {})
            novelty_filter = AgenticNoveltyFilter(provider=provider)

            assessment = novelty_filter.assess(
                problem_spec=_problem_spec(),
                candidate=_strong_candidate(),
                archive_nodes=[],
            )

        self.assertTrue(assessment.is_novel)
        self.assertEqual(assessment.novelty_score, 1.0)
        self.assertEqual(provider.calls, [])

    def test_agentic_novelty_filter_delegates_semantic_judgment_to_provider(self) -> None:
        assessment = NoveltyAssessment(
            novelty_score=0.18,
            max_similarity=0.82,
            nearest_neighbor_id="node-0001",
            similarity_threshold=0.8,
            is_novel=False,
            summary="This is mostly a rephrasing of the archived workflow-native idea.",
            duplicate_signals=["Same underlying mechanism.", "Similar rollout plan."],
        )
        with TemporaryDirectory() as directory:
            provider = FakeProvider(Path(directory), {"assess_novelty": assessment})
            novelty_filter = AgenticNoveltyFilter(provider=provider)

            result = novelty_filter.assess(
                problem_spec=_problem_spec(),
                candidate=_near_duplicate_candidate(),
                archive_nodes=[_node("node-0001", novelty_score=0.55)],
            )

        self.assertEqual(result, assessment)
        self.assertEqual(provider.calls[0]["action_name"], "assess_novelty")
        self.assertEqual(
            provider.calls[0]["input_payload"]["archive_candidates"][0]["node_id"],
            "node-0001",
        )


class SchemaValidationTests(unittest.TestCase):
    def test_evaluation_assessment_rejects_unknown_keys(self) -> None:
        with self.assertRaises(ArgusValidationError):
            EvaluationAssessment.from_dict(
                {
                    "score": _strong_score().to_dict(),
                    "summary": "ok",
                    "strengths": [],
                    "weaknesses": [],
                    "open_questions": [],
                    "unexpected": True,
                }
            )

    def test_novelty_assessment_rejects_blank_summary(self) -> None:
        with self.assertRaises(ArgusValidationError):
            NoveltyAssessment.from_dict(
                {
                    "novelty_score": 0.8,
                    "max_similarity": 0.2,
                    "nearest_neighbor_id": None,
                    "similarity_threshold": 0.8,
                    "is_novel": True,
                    "summary": "   ",
                    "duplicate_signals": [],
                }
            )

    def test_pairwise_ranking_assessment_rejects_invalid_winner(self) -> None:
        with self.assertRaises(ArgusValidationError):
            PairwiseRankingAssessment.from_dict(
                {
                    "winner": "tie",
                    "summary": "invalid",
                    "decisive_advantages": [],
                    "decisive_risks": [],
                    "confidence": 0.5,
                }
            )


class FakeProvider:
    name = "fake"

    def __init__(self, root_dir: Path, responses: dict[str, object]) -> None:
        self.root_dir = root_dir
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def run_action(
        self,
        *,
        action_name: ActionType | str,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
        output_schema,
    ):
        self.calls.append(
            {
                "action_name": action_name.value if isinstance(action_name, ActionType) else action_name,
                "problem_spec": problem_spec,
                "input_payload": input_payload,
            }
        )
        normalized_action = action_name.value if isinstance(action_name, ActionType) else action_name
        payload = self.responses[normalized_action]
        artifacts_dir = self.root_dir / normalized_action
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifacts = ProviderArtifacts(
            invocation_id=normalized_action,
            invocation_dir=artifacts_dir,
            prompt_path=artifacts_dir / "prompt.md",
            schema_path=artifacts_dir / "schema.json",
            last_message_path=artifacts_dir / "last-message.json",
            response_path=artifacts_dir / "response.json",
            stdout_path=artifacts_dir / "stdout.jsonl",
            stderr_path=artifacts_dir / "stderr.txt",
            metadata_path=artifacts_dir / "metadata.json",
            sandbox_dir=artifacts_dir / "workspace",
            failure_path=artifacts_dir / "failure.json",
        )
        return ProviderResponse(
            provider_name=self.name,
            action_name=normalized_action,
            payload=payload,
            raw_payload=payload.to_dict(),
            prompt_sha256="fake",
            artifacts=artifacts,
            exit_status=0,
            timestamp=datetime(2026, 3, 6, 3, 33, 40, tzinfo=timezone.utc),
            model="fake-model",
        )


def _problem_spec() -> ProblemSpec:
    return ProblemSpec(
        request="Design a local-first brainstorming engine for product teams.",
        constraints=["Local-first only.", "No sales-assisted onboarding."],
        success_criteria=[
            "Increase retention through workflow lock-in.",
            "Keep setup self-serve.",
        ],
        context={"segment": "product"},
    )


def _strong_candidate() -> Candidate:
    return Candidate(
        thesis="Ship a workflow-native local-first engine that compounds team knowledge.",
        mechanism=(
            "Persist every decision branch on-device, score each branch against retention "
            "signals, and roll out a self-serve pilot that measures workflow lock-in."
        ),
        assumptions=[
            "Teams will configure a lightweight workflow if the output quality is durable."
        ],
        strengths=[
            "Creates workflow lock-in without requiring services-heavy onboarding.",
            "Improves retention by preserving reusable decision paths.",
        ],
        failure_modes=["Could feel heavy if the first-run workflow setup is unclear."],
        unknowns=["How much configuration will self-serve teams tolerate before activation drops?"],
        implementation_shape=(
            "Start with an on-device prototype, instrument activation and retention, "
            "then phase in shared templates."
        ),
        evidence=[
            "The product brief prioritizes local-first behavior and workflow retention "
            "over decorative brainstorming."
        ],
    )


def _near_duplicate_candidate() -> Candidate:
    return Candidate(
        thesis="Build a workflow-native local-first engine for product teams.",
        mechanism=(
            "Persist every decision branch on device, score branches against retention, "
            "and ship a self-serve pilot before expansion."
        ),
        assumptions=["Teams will accept lightweight workflow setup for stronger outputs."],
        strengths=["Creates workflow lock-in for product teams."],
        failure_modes=["Could feel heavy if setup is confusing."],
        unknowns=["How much setup friction will teams tolerate?"],
        implementation_shape="Start with an on-device prototype and phase in shared templates.",
        evidence=["The brief prioritizes local-first behavior and retention."],
    )


def _strong_score() -> ScoreVector:
    return ScoreVector(
        hard_constraint_pass=True,
        hard_constraint_reasons=[],
        distinctiveness=0.72,
        usefulness=0.84,
        specificity=0.81,
        plausibility=0.79,
        implementation_tractability=0.77,
        upside=0.83,
        adversarial_robustness=0.69,
        evidence_quality=0.74,
        total_score=5.19,
        confidence_estimate=0.82,
    )


def _node(
    node_id: str,
    *,
    total_score: float | None = None,
    confidence: float = 0.5,
    novelty_score: float,
    score: ScoreVector | object | None = _DEFAULT_SCORE,
) -> Node:
    if score is _DEFAULT_SCORE:
        resolved_score: ScoreVector | None = ScoreVector(
            hard_constraint_pass=True,
            hard_constraint_reasons=[],
            distinctiveness=0.5,
            usefulness=0.6,
            specificity=0.6,
            plausibility=0.6,
            implementation_tractability=0.6,
            upside=0.6,
            adversarial_robustness=0.6,
            evidence_quality=0.6,
            total_score=0.0 if total_score is None else total_score,
            confidence_estimate=confidence,
        )
    elif score is None or isinstance(score, ScoreVector):
        resolved_score = score
    else:
        raise TypeError("score must be a ScoreVector, None, or the default sentinel.")

    return Node(
        node_id=node_id,
        parent_ids=[],
        depth=0,
        action_type=ActionType.GENERATE_SEED,
        provider_name="codex",
        candidate=_strong_candidate(),
        score=resolved_score,
        novelty_score=novelty_score,
        lifecycle_status=NodeLifecycleStatus.ADMITTED,
        metadata={},
        created_at=datetime(2026, 3, 6, 3, 33, 40, tzinfo=timezone.utc),
    )
