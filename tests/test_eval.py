from __future__ import annotations

from datetime import datetime, timezone
import unittest

from argus.errors import ArgusValidationError
from argus.eval import (
    DEFAULT_EVALUATOR_WEIGHTS,
    DeterministicEvaluator,
    NoveltyConfig,
    TextNoveltyFilter,
    rank_nodes,
)
from argus.models import (
    ActionType,
    Candidate,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
)


class EvaluatorTests(unittest.TestCase):
    def test_evaluator_scores_supported_candidate_with_explicit_weights(self) -> None:
        evaluator = DeterministicEvaluator()

        score = evaluator.evaluate(
            _problem_spec(),
            _strong_candidate(),
            novelty_score=0.81,
        )

        self.assertTrue(score.hard_constraint_pass)
        self.assertEqual(score.hard_constraint_reasons, [])
        self.assertGreater(score.usefulness, 0.75)
        self.assertGreater(score.implementation_tractability, 0.9)
        self.assertAlmostEqual(
            score.total_score,
            round(
                score.distinctiveness * DEFAULT_EVALUATOR_WEIGHTS.distinctiveness
                + score.usefulness * DEFAULT_EVALUATOR_WEIGHTS.usefulness
                + score.specificity * DEFAULT_EVALUATOR_WEIGHTS.specificity
                + score.plausibility * DEFAULT_EVALUATOR_WEIGHTS.plausibility
                + score.implementation_tractability
                * DEFAULT_EVALUATOR_WEIGHTS.implementation_tractability
                + score.upside * DEFAULT_EVALUATOR_WEIGHTS.upside
                + score.adversarial_robustness
                * DEFAULT_EVALUATOR_WEIGHTS.adversarial_robustness
                + score.evidence_quality * DEFAULT_EVALUATOR_WEIGHTS.evidence_quality,
                4,
            ),
        )
        self.assertGreater(score.confidence_estimate, 0.6)

    def test_evaluator_flags_hard_constraint_violation_and_zeroes_total(self) -> None:
        evaluator = DeterministicEvaluator()

        score = evaluator.evaluate(
            _problem_spec(),
            Candidate(
                thesis="Use a white-glove sales team to sell consulting packages.",
                mechanism="Add account executives who run custom onboarding workshops for each buyer.",
                assumptions=["Enterprise deals will pay for bespoke support."],
                strengths=["Could raise contract value."],
                failure_modes=["Requires a field team."],
                unknowns=["How large can the sales motion grow?"],
                evidence=["Some enterprise buyers like hands-on onboarding."],
            ),
            novelty_score=0.2,
        )

        self.assertFalse(score.hard_constraint_pass)
        self.assertIn(
            "Candidate appears to violate constraint: No sales-assisted onboarding.",
            score.hard_constraint_reasons,
        )
        self.assertEqual(score.total_score, 0.0)
        self.assertLess(score.confidence_estimate, 0.5)

    def test_rank_nodes_orders_passing_nodes_ahead_of_failed_nodes(self) -> None:
        evaluator = DeterministicEvaluator()
        strong_score = evaluator.evaluate(_problem_spec(), _strong_candidate(), novelty_score=0.81)
        weaker_score = evaluator.evaluate(_problem_spec(), _weaker_candidate(), novelty_score=0.43)
        failed_score = evaluator.evaluate(
            _problem_spec(),
            Candidate(
                thesis="Use a services-heavy launch plan.",
                mechanism="Hire consultants to onboard every team manually and customize the workflow.",
                assumptions=["Hands-on setup will fix adoption."],
                strengths=["Lets the team control every rollout."],
                failure_modes=["Services costs scale badly."],
                unknowns=["How many consultants would be required?"],
                evidence=["Enterprise buyers sometimes accept support-heavy onboarding."],
            ),
            novelty_score=0.33,
        )

        ranked = rank_nodes(
            [
                _node("node-003", _weaker_candidate(), weaker_score, novelty_score=0.43),
                _node("node-002", _strong_candidate(), strong_score, novelty_score=0.81),
                _node(
                    "node-001",
                    Candidate(
                        thesis="Use a services-heavy launch plan.",
                        mechanism="Hire consultants to onboard every team manually and customize the workflow.",
                        assumptions=["Hands-on setup will fix adoption."],
                        strengths=["Lets the team control every rollout."],
                        failure_modes=["Services costs scale badly."],
                        unknowns=["How many consultants would be required?"],
                        evidence=["Enterprise buyers sometimes accept support-heavy onboarding."],
                    ),
                    failed_score,
                    novelty_score=0.33,
                ),
            ]
        )

        self.assertEqual([node.node_id for node in ranked], ["node-002", "node-003", "node-001"])

    def test_rank_nodes_requires_scores(self) -> None:
        with self.assertRaises(ArgusValidationError):
            rank_nodes([_node("node-999", _strong_candidate(), None, novelty_score=0.6)])


class NoveltyFilterTests(unittest.TestCase):
    def test_novelty_filter_rejects_near_duplicate_candidate(self) -> None:
        novelty_filter = TextNoveltyFilter()
        archive = [
            _node(
                "node-0001",
                _strong_candidate(),
                None,
                novelty_score=0.55,
                lifecycle_status=NodeLifecycleStatus.ARCHIVED,
            )
        ]

        assessment = novelty_filter.assess(_near_duplicate_candidate(), archive)

        self.assertFalse(assessment.is_novel)
        self.assertEqual(assessment.nearest_neighbor_id, "node-0001")
        self.assertGreaterEqual(
            assessment.max_similarity,
            NoveltyConfig().similarity_threshold,
        )
        self.assertLess(assessment.novelty_score, 0.25)

    def test_novelty_filter_accepts_distinct_candidate(self) -> None:
        novelty_filter = TextNoveltyFilter()
        archive = [
            _node(
                "node-0001",
                _strong_candidate(),
                None,
                novelty_score=0.55,
                lifecycle_status=NodeLifecycleStatus.ARCHIVED,
            )
        ]

        assessment = novelty_filter.assess(_distinct_candidate(), archive)

        self.assertTrue(assessment.is_novel)
        self.assertEqual(assessment.nearest_neighbor_id, "node-0001")
        self.assertLess(assessment.max_similarity, 0.4)
        self.assertGreater(assessment.novelty_score, 0.6)


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
            "Persist every decision branch on-device, score each branch against "
            "retention signals, and roll out a self-serve pilot that measures "
            "workflow lock-in before deeper expansion."
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
            "Persist every decision branch on device, score branches against "
            "retention, and ship a self-serve pilot before expansion."
        ),
        assumptions=["Teams will accept lightweight workflow setup for stronger outputs."],
        strengths=["Creates workflow lock-in for product teams."],
        failure_modes=["Could feel heavy if setup is confusing."],
        unknowns=["How much setup friction will teams tolerate?"],
        implementation_shape="Start with an on-device prototype and phase in shared templates.",
        evidence=["The brief prioritizes local-first behavior and retention."],
    )


def _weaker_candidate() -> Candidate:
    return Candidate(
        thesis="Offer reusable workflow templates with lighter customization.",
        mechanism=(
            "Ship a local-first template library, let teams copy proven decision "
            "flows, and instrument activation before adding deeper workflow scoring."
        ),
        assumptions=["Teams prefer lighter setup over bespoke workflows."],
        strengths=["Improves activation while staying self-serve."],
        failure_modes=["Could create weaker lock-in than deeper workflow capture."],
        unknowns=["Whether templates alone can materially improve retention."],
        implementation_shape=(
            "Launch with five templates, track reuse, and deepen only the templates "
            "that change retention."
        ),
        evidence=["Template reuse can shorten setup time for self-serve teams."],
    )


def _distinct_candidate() -> Candidate:
    return Candidate(
        thesis="Turn the engine into a facilitator for live strategy workshops.",
        mechanism=(
            "Generate timed prompts for a moderator, capture spoken objections, and "
            "export workshop summaries for later review."
        ),
        assumptions=["Teams prefer synchronous sessions over persistent workflows."],
        strengths=["Fits teams that already plan together live."],
        failure_modes=["Does not create durable workflow lock-in."],
        unknowns=["Whether asynchronous users would return later."],
        implementation_shape="Start with a lightweight meeting mode and transcript export.",
        evidence=["Some teams already run strategy workshops in a shared call."],
    )


def _node(
    node_id: str,
    candidate: Candidate,
    score,
    *,
    novelty_score: float,
    lifecycle_status: NodeLifecycleStatus = NodeLifecycleStatus.ADMITTED,
) -> Node:
    return Node(
        node_id=node_id,
        parent_ids=[],
        depth=0,
        action_type=ActionType.GENERATE_SEED,
        provider_name="codex",
        candidate=candidate,
        score=score,
        novelty_score=novelty_score,
        lifecycle_status=lifecycle_status,
        metadata={},
        created_at=datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc),
    )
