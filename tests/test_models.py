from __future__ import annotations

from datetime import datetime, timezone
import unittest

from argus.errors import ArgusValidationError
from argus.models import (
    ActionType,
    Candidate,
    Critique,
    FinalRecommendation,
    LearningEvidenceSource,
    LearningMemory,
    LearningNote,
    LearningNoteType,
    Node,
    NodeLifecycleStatus,
    OutcomeFeedback,
    OutcomeFeedbackLedger,
    OutcomeFeedbackStatus,
    PairwiseDecisionArtifact,
    ProblemSpec,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    ScoreVector,
    SearchIsland,
    SearchState,
)


class ModelTests(unittest.TestCase):
    def test_problem_spec_round_trips_with_normalized_context(self) -> None:
        spec = ProblemSpec(
            request="  Find the right architecture for Argus.  ",
            constraints=[" Local-first ", " Python 3.12 "],
            success_criteria=[" actionable ", " reproducible "],
            context={"z": 1, "nested": {"b": True, "a": " value "}},
        )

        payload = spec.to_dict()
        restored = ProblemSpec.from_dict(payload)

        self.assertEqual(spec, restored)
        self.assertEqual(payload["request"], "Find the right architecture for Argus.")
        self.assertEqual(list(payload["context"]), ["nested", "z"])

    def test_candidate_projection_is_stable_and_omits_missing_optional_text(self) -> None:
        candidate = Candidate(
            thesis="Ship a deterministic search loop.",
            mechanism="Persist candidates and score before expanding.",
            assumptions=["Operators want reproducibility."],
            strengths=["Improves auditability."],
            failure_modes=["May prune too aggressively."],
            unknowns=["How much state is too much state?"],
            evidence=["Spec requires replayable runs."],
        )

        projection = candidate.text_projection()

        self.assertIn("thesis:", projection)
        self.assertIn("- Ship a deterministic search loop.", projection)
        self.assertNotIn("implementation_shape", projection)

    def test_score_vector_requires_reasons_for_hard_constraint_failure(self) -> None:
        with self.assertRaises(ArgusValidationError):
            ScoreVector(
                hard_constraint_pass=False,
                hard_constraint_reasons=[],
                distinctiveness=0.3,
                usefulness=0.4,
                specificity=0.5,
                plausibility=0.6,
                implementation_tractability=0.7,
                upside=0.8,
                adversarial_robustness=0.5,
                evidence_quality=0.4,
                total_score=3.2,
                confidence_estimate=0.5,
            )

    def test_node_round_trips_nested_models_and_timestamp(self) -> None:
        node = Node(
            node_id="node-0001",
            parent_ids=[],
            depth=0,
            action_type=ActionType.FRAME_PROBLEM,
            provider_name="codex",
            candidate=_sample_candidate(),
            island_id="balanced",
            score=_sample_score(),
            critique=_sample_critique(),
            novelty_score=0.72,
            lifecycle_status=NodeLifecycleStatus.ADMITTED,
            metadata={"attempt": 1, "flags": {"local_only": True}},
            created_at=datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc),
        )

        payload = node.to_dict()
        restored = Node.from_dict(payload)

        self.assertEqual(node, restored)
        self.assertEqual(payload["created_at"], "2026-03-06T02:04:56Z")
        self.assertEqual(payload["action_type"], "frame_problem")

    def test_search_state_round_trips_with_node_consistency_checks(self) -> None:
        node = Node(
            node_id="node-0001",
            parent_ids=[],
            depth=0,
            action_type=ActionType.FRAME_PROBLEM,
            provider_name="codex",
            candidate=_sample_candidate(),
            island_id="balanced",
            score=_sample_score(),
            novelty_score=0.61,
            lifecycle_status=NodeLifecycleStatus.ARCHIVED,
            metadata={"step": 1},
            created_at=datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc),
        )
        state = SearchState(
            problem_spec=ProblemSpec(
                request="Find the best retention strategy.",
                constraints=["Stay self-serve."],
                success_criteria=["Increase activation."],
                context={"team": "growth"},
            ),
            root_id="node-0001",
            nodes={"node-0001": node},
            archive_ids=["node-0001"],
            frontier_ids=["node-0001"],
            pruned_ids=[],
            winner_ids=[],
            islands={
                "balanced": SearchIsland(
                    island_id="balanced",
                    label="Balanced",
                    description="Balanced exploration.",
                    archive_ids=["node-0001"],
                    frontier_ids=["node-0001"],
                    pruned_ids=[],
                )
            },
            learning_notes=[
                LearningNote(
                    note_type=LearningNoteType.CONSTRAINT,
                    text="Self-serve onboarding cannot absorb enterprise setup work.",
                    source_node_ids=["node-0001"],
                )
            ],
            budget_spent=1,
            step_count=1,
        )

        payload = state.to_dict()
        restored = SearchState.from_dict(payload)

        self.assertEqual(state, restored)
        self.assertEqual(list(payload["nodes"]), ["node-0001"])
        self.assertEqual(payload["nodes"]["node-0001"]["island_id"], "balanced")
        self.assertEqual(list(payload["islands"]), ["balanced"])

    def test_search_state_rejects_unknown_learning_note_sources(self) -> None:
        node = Node(
            node_id="node-0001",
            parent_ids=[],
            depth=0,
            action_type=ActionType.FRAME_PROBLEM,
            provider_name="codex",
            candidate=_sample_candidate(),
            novelty_score=0.4,
            lifecycle_status=NodeLifecycleStatus.ADMITTED,
            metadata={},
            created_at=datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc),
        )

        with self.assertRaises(ArgusValidationError):
            SearchState(
                problem_spec=ProblemSpec(
                    request="Find the right product strategy.",
                    constraints=[],
                    success_criteria=["Make a high-quality decision."],
                    context={},
                ),
                root_id="node-0001",
                nodes={"node-0001": node},
                archive_ids=["node-0001"],
                frontier_ids=[],
                pruned_ids=[],
                winner_ids=[],
                islands={
                    "balanced": SearchIsland(
                        island_id="balanced",
                        label="Balanced",
                        description="Balanced exploration.",
                        archive_ids=["node-0001"],
                        frontier_ids=[],
                        pruned_ids=[],
                    )
                },
                learning_notes=[
                    LearningNote(
                        note_type=LearningNoteType.SUMMARY,
                        text="This note points at a missing node.",
                        source_node_ids=["node-9999"],
                    )
                ],
                budget_spent=0,
                step_count=0,
            )

    def test_final_recommendation_round_trips_extended_fields(self) -> None:
        recommendation = FinalRecommendation(
            best_bet_node_id="node-0007",
            conservative_node_id="node-0003",
            high_upside_node_id="node-0011",
            rejected_but_insightful_ids=["node-0002"],
            summary_markdown="Prefer the workflow-native bet.",
            next_experiments=["Interview five current users.", "Prototype the scoring rubric."],
            assumptions=["Users will trade setup time for better outputs."],
            failure_modes=["Onboarding friction may outweigh output quality gains."],
            reversal_conditions=["If interviews show low willingness to configure workflows."],
            pairwise_decisions=[
                PairwiseDecisionArtifact(
                    selection_label="Best bet",
                    objective_name="best_overall",
                    objective_description="Choose the strongest overall recommendation.",
                    left_node_id="node-0007",
                    right_node_id="node-0003",
                    winner_node_id="node-0007",
                    summary="The workflow-native bet has stronger compounding value.",
                    decisive_advantages=["Builds a durable recurring ritual."],
                    decisive_risks=["Needs careful onboarding."],
                    confidence=0.82,
                )
            ],
        )

        payload = recommendation.to_dict()
        restored = FinalRecommendation.from_dict(payload)

        self.assertEqual(recommendation, restored)
        self.assertIn("assumptions", payload)
        self.assertIn("reversal_conditions", payload)
        self.assertEqual(payload["pairwise_decisions"][0]["winner_node_id"], "node-0007")

    def test_pairwise_decision_artifact_rejects_unknown_winner_side(self) -> None:
        with self.assertRaises(ArgusValidationError):
            PairwiseDecisionArtifact(
                selection_label="Best bet",
                objective_name="best_overall",
                objective_description="Choose the strongest overall recommendation.",
                left_node_id="node-0001",
                right_node_id="node-0002",
                winner_node_id="node-9999",
                summary="Invalid winner reference.",
                decisive_advantages=[],
                decisive_risks=[],
                confidence=0.5,
            )

    def test_learning_memory_round_trips_and_selects_relevant_entries(self) -> None:
        product_problem = ProblemSpec(
            request="Design the best retention strategy for a workflow-heavy product.",
            constraints=["Keep the system auditable."],
            success_criteria=["Increase repeated usage."],
            context={"family": "product"},
        )
        architecture_problem = ProblemSpec(
            request="Design the best local-first architecture for Argus.",
            constraints=["Keep the runtime deterministic."],
            success_criteria=["Preserve replayability."],
            context={"family": "architecture"},
        )
        memory = LearningMemory.empty().merge_observations(
            run_id="run-product-a",
            problem_spec=product_problem,
            notes=[
                LearningNote(
                    note_type=LearningNoteType.WINNING_PATTERN,
                    text="Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
                    source_node_ids=["node-0003"],
                )
            ],
            observed_at=datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc),
        )
        memory = memory.merge_observations(
            run_id="run-product-b",
            problem_spec=product_problem,
            notes=[
                LearningNote(
                    note_type=LearningNoteType.WINNING_PATTERN,
                    text="Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
                    source_node_ids=["node-0007"],
                )
            ],
            observed_at=datetime(2026, 3, 6, 2, 10, 0, tzinfo=timezone.utc),
        )
        memory = memory.merge_observations(
            run_id="run-architecture-a",
            problem_spec=architecture_problem,
            notes=[
                LearningNote(
                    note_type=LearningNoteType.CONSTRAINT,
                    text="Local-first systems need explicit sync conflict handling and replay-safe logs.",
                    source_node_ids=["node-0011"],
                )
            ],
            observed_at=datetime(2026, 3, 6, 2, 12, 0, tzinfo=timezone.utc),
        )

        payload = memory.to_dict()
        restored = LearningMemory.from_dict(payload)
        selected = restored.select_for_problem(product_problem, limit=1)

        self.assertEqual(memory, restored)
        self.assertEqual(len(restored.entries), 2)
        workflow_entry = restored.entries[0]
        self.assertEqual(workflow_entry.observation_count, 2)
        self.assertEqual(workflow_entry.source_run_ids, ["run-product-a", "run-product-b"])
        self.assertEqual(
            selected.entries[0].text,
            "Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
        )
        self.assertEqual(
            workflow_entry.evidence_sources,
            [LearningEvidenceSource.SEARCH_RUN],
        )

    def test_outcome_feedback_round_trips_through_ledger(self) -> None:
        feedback = OutcomeFeedback(
            feedback_id="feedback-20260306T021500Z",
            run_id="run-20260306T020500Z",
            node_id="node-0007",
            candidate_thesis="Workflow-native archive with weekly decision reviews",
            problem_statement="Find the best retention strategy for a workflow-heavy product.",
            outcome_status=OutcomeFeedbackStatus.VALIDATED,
            summary="The pilot retained teams because the archive made weekly reviews faster.",
            learning_notes=[
                LearningNote(
                    note_type=LearningNoteType.WINNING_PATTERN,
                    text="Teams accept setup work when the audit trail immediately improves recurring reviews.",
                    source_node_ids=["node-0007"],
                )
            ],
            evidence=["Pilot cohort retained 4 of 5 teams after three weeks."],
            experiment_label="weekly-review-pilot",
            recorded_at=datetime(2026, 3, 6, 2, 15, 0, tzinfo=timezone.utc),
        )

        payload = OutcomeFeedbackLedger.empty().append(feedback).to_dict()
        restored = OutcomeFeedbackLedger.from_dict(payload)

        self.assertEqual(len(restored.entries), 1)
        self.assertEqual(restored.entries[0], feedback)

    def test_learning_memory_prioritizes_outcome_backed_notes_when_overlap_ties(self) -> None:
        problem = ProblemSpec(
            request="Audit trail setup artifact",
            constraints=[],
            success_criteria=[],
            context={},
        )
        memory = LearningMemory.empty().merge_observations(
            run_id="run-search",
            problem_spec=problem,
            notes=[
                LearningNote(
                    note_type=LearningNoteType.SUMMARY,
                    text="Audit trail setup artifact",
                    source_node_ids=["node-0001"],
                )
            ],
            observed_at=datetime(2026, 3, 6, 2, 5, 0, tzinfo=timezone.utc),
        )
        feedback = OutcomeFeedback(
            feedback_id="feedback-20260306T021600Z",
            run_id="run-search",
            node_id="node-0002",
            candidate_thesis="Audit-first workflow",
            problem_statement=problem.request,
            outcome_status=OutcomeFeedbackStatus.MIXED,
            summary="The audit artifact helped, but the initial setup still needed coaching.",
            learning_notes=[
                LearningNote(
                    note_type=LearningNoteType.SUMMARY,
                    text="Artifact setup audit trail",
                    source_node_ids=["node-0002"],
                )
            ],
            evidence=[],
            recorded_at=datetime(2026, 3, 6, 2, 16, 0, tzinfo=timezone.utc),
        )

        selected = memory.merge_outcome_feedback(feedback).select_for_problem(problem, limit=1)

        self.assertEqual(len(selected.entries), 1)
        self.assertEqual(
            selected.entries[0].evidence_sources,
            [LearningEvidenceSource.OUTCOME_FEEDBACK],
        )

    def test_provider_routing_stats_round_trip_with_derived_averages(self) -> None:
        stats = ProviderRoutingStats(
            entries=[
                ProviderRoutingStatsEntry(
                    provider_name="codex",
                    action_name="generate_seed",
                    run_count=1,
                    invocation_count=2,
                    provider_failure_count=0,
                    candidate_count=4,
                    scored_node_count=4,
                    admitted_count=3,
                    rejected_count=0,
                    hard_fail_count=1,
                    strong_score_count=2,
                    stress_test_survivor_count=1,
                    winner_count=1,
                    winner_contribution_count=2,
                    critique_count=0,
                    useful_critique_count=0,
                    learning_note_count=0,
                    accumulated_score=23.41,
                    total_reward=8.5,
                    last_run_id="run-20260306T020456Z",
                    last_updated_at=datetime(2026, 3, 6, 2, 10, 0, tzinfo=timezone.utc),
                )
            ],
            updated_at=datetime(2026, 3, 6, 2, 10, 0, tzinfo=timezone.utc),
        )

        payload = stats.to_dict()
        restored = ProviderRoutingStats.from_dict(payload)

        self.assertEqual(stats, restored)
        self.assertEqual(payload["entries"][0]["average_reward"], 4.25)
        self.assertAlmostEqual(payload["entries"][0]["average_score"], 5.8525)

    def test_provider_routing_stats_merge_accumulates_matching_entries(self) -> None:
        earlier = ProviderRoutingStats(
            entries=[
                ProviderRoutingStatsEntry(
                    provider_name="codex",
                    action_name="stress_test",
                    run_count=1,
                    invocation_count=2,
                    provider_failure_count=0,
                    candidate_count=0,
                    scored_node_count=0,
                    admitted_count=0,
                    rejected_count=0,
                    hard_fail_count=0,
                    strong_score_count=0,
                    stress_test_survivor_count=0,
                    winner_count=0,
                    winner_contribution_count=0,
                    critique_count=2,
                    useful_critique_count=2,
                    learning_note_count=0,
                    accumulated_score=0.0,
                    total_reward=2.0,
                    last_run_id="run-1",
                    last_updated_at=datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc),
                )
            ],
            updated_at=datetime(2026, 3, 6, 2, 0, 0, tzinfo=timezone.utc),
        )
        later = ProviderRoutingStats(
            entries=[
                ProviderRoutingStatsEntry(
                    provider_name="codex",
                    action_name="stress_test",
                    run_count=1,
                    invocation_count=1,
                    provider_failure_count=1,
                    candidate_count=0,
                    scored_node_count=0,
                    admitted_count=0,
                    rejected_count=0,
                    hard_fail_count=0,
                    strong_score_count=0,
                    stress_test_survivor_count=0,
                    winner_count=0,
                    winner_contribution_count=0,
                    critique_count=0,
                    useful_critique_count=0,
                    learning_note_count=0,
                    accumulated_score=0.0,
                    total_reward=-2.0,
                    last_run_id="run-2",
                    last_updated_at=datetime(2026, 3, 6, 3, 0, 0, tzinfo=timezone.utc),
                )
            ],
            updated_at=datetime(2026, 3, 6, 3, 0, 0, tzinfo=timezone.utc),
        )

        merged = earlier.merge(later)

        self.assertEqual(len(merged.entries), 1)
        entry = merged.entries[0]
        self.assertEqual(entry.run_count, 2)
        self.assertEqual(entry.invocation_count, 3)
        self.assertEqual(entry.provider_failure_count, 1)
        self.assertEqual(entry.critique_count, 2)
        self.assertEqual(entry.last_run_id, "run-2")
        self.assertEqual(entry.total_reward, 0.0)

    def test_from_dict_rejects_unknown_top_level_keys(self) -> None:
        with self.assertRaises(ArgusValidationError):
            ProblemSpec.from_dict(
                {
                    "request": "Find the right moat.",
                    "constraints": [],
                    "success_criteria": [],
                    "context": {},
                    "unexpected": "value",
                }
            )


def _sample_candidate() -> Candidate:
    return Candidate(
        thesis="Bias the search toward operationally credible bets.",
        mechanism="Score implementation tractability before deepening.",
        assumptions=["The operator values actionability over novelty alone."],
        strengths=["Reduces decorative ideas."],
        failure_modes=["Can underweight disruptive bets."],
        unknowns=["How much upside should offset execution risk?"],
        implementation_shape="Deterministic evaluator plus archived nodes.",
        evidence=["Specs emphasize evaluator-first logic."],
    )


def _sample_score() -> ScoreVector:
    return ScoreVector(
        hard_constraint_pass=True,
        hard_constraint_reasons=[],
        distinctiveness=0.63,
        usefulness=0.81,
        specificity=0.74,
        plausibility=0.79,
        implementation_tractability=0.77,
        upside=0.69,
        adversarial_robustness=0.72,
        evidence_quality=0.65,
        total_score=5.8,
        confidence_estimate=0.76,
    )


def _sample_critique() -> Critique:
    return Critique(
        hidden_dependencies=["Needs stable scoring weights."],
        kill_shots=["Fails if provider output is not schema-validated."],
        sharp_edges=["Could converge too early without novelty filtering."],
        summary="Strong foundation, but only if validation is strict.",
    )
