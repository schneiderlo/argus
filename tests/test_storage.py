from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from argus.errors import ArgusValidationError
from argus.models import (
    AdversarialReview,
    ActionType,
    Candidate,
    ComparisonMatrix,
    ComparisonMatrixRow,
    CoverageLedger,
    CoverageStatus,
    Critique,
    DeepDiveDoc,
    FinalRecommendation,
    FinalDecisionDoc,
    LearningEvidenceSource,
    LearningMemory,
    LearningNote,
    LearningNoteType,
    Node,
    NodeLifecycleStatus,
    OutcomeFeedback,
    OutcomeFeedbackStatus,
    PairwiseDecisionArtifact,
    ProblemSpec,
    ProposalBrief,
    ProposalDisposition,
    ProposalTriageDecision,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    ResearchSchedulerAction,
    ResearchArtifactBundle,
    SchedulerDecision,
    ScoreVector,
    SearchAxis,
    SearchCell,
    SearchIsland,
    SearchSpaceFrame,
    SearchState,
    TriageReport,
)
from argus.storage import FileSystemStateStore, RunStatus


class FileSystemStateStoreTests(unittest.TestCase):
    def test_store_persists_snapshot_with_split_artifacts_and_replays_it(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            created_at = datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc)
            problem_spec = _sample_problem_spec()
            state = _sample_search_state(problem_spec)
            recommendation = _sample_final_recommendation()

            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020456Z",
                created_at=created_at,
                metadata={"operator": "ralph"},
            )
            refreshed_manifest = store.save_snapshot(
                manifest.run_id,
                state=state,
                final_recommendation=recommendation,
                summary_markdown="Prefer the workflow-native bet.",
                status=RunStatus.COMPLETED,
                updated_at=created_at,
                metadata_patch={"winner_count": 1},
            )

            run_dir = store.root_dir / manifest.run_id
            self.assertTrue((run_dir / "run.json").is_file())
            self.assertTrue((run_dir / "problem-spec.json").is_file())
            self.assertTrue((run_dir / "state.json").is_file())
            self.assertTrue((run_dir / "learning-notes.json").is_file())
            self.assertTrue((run_dir / "final-recommendation.json").is_file())
            self.assertTrue((run_dir / "summary.md").is_file())
            self.assertTrue((run_dir / "nodes" / "node-0001.json").is_file())
            self.assertTrue((run_dir / "scores" / "node-0001.json").is_file())
            self.assertTrue((run_dir / "critiques" / "node-0001.json").is_file())

            raw_node_payload = json.loads(
                (run_dir / "nodes" / "node-0001.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("score", raw_node_payload)
            self.assertNotIn("critique", raw_node_payload)

            loaded = store.load_run(manifest.run_id)

        self.assertEqual(loaded.manifest, refreshed_manifest)
        self.assertEqual(loaded.problem_spec, problem_spec)
        self.assertEqual(loaded.state, state)
        self.assertEqual(loaded.final_recommendation, recommendation)
        self.assertEqual(
            loaded.final_recommendation.pairwise_decisions[0].objective_name,
            "best_overall",
        )
        self.assertEqual(loaded.summary_markdown, "Prefer the workflow-native bet.")
        self.assertEqual(loaded.manifest.metadata["winner_count"], 1)

    def test_store_persists_research_bundle_and_rendered_markdown(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            state = _sample_search_state(problem_spec)
            bundle = _sample_research_bundle()
            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020456Z-research",
            )

            refreshed_manifest = store.save_snapshot(
                manifest.run_id,
                state=state,
                research_bundle=bundle,
                research_markdown={
                    "search-space-frame.md": "# Search Space\n",
                    "coverage-ledger.md": "# Ledger\n",
                    "final-decision.md": "# Final Decision\n",
                    "proposals/proposal-b.md": "# Proposal B\n",
                },
                final_recommendation=_sample_final_recommendation(),
                summary_markdown="Prefer the coverage-led path.",
                status=RunStatus.COMPLETED,
            )

            run_dir = store.root_dir / manifest.run_id
            loaded = store.load_run(manifest.run_id)
            self.assertEqual(refreshed_manifest.research_bundle_path, "research/bundle.json")
            self.assertEqual(refreshed_manifest.research_artifacts_dir, "research/markdown")
            self.assertTrue((run_dir / "research" / "bundle.json").is_file())
            self.assertTrue((run_dir / "research" / "markdown" / "search-space-frame.md").is_file())
            self.assertTrue((run_dir / "research" / "markdown" / "proposals" / "proposal-b.md").is_file())
            self.assertEqual(loaded.research_bundle, bundle)

    def test_save_snapshot_rejects_final_recommendations_with_unknown_node_ids(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            state = _sample_search_state(problem_spec)
            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020457Z",
            )

            with self.assertRaises(ArgusValidationError):
                store.save_snapshot(
                    manifest.run_id,
                    state=state,
                    final_recommendation=FinalRecommendation(
                        best_bet_node_id="node-9999",
                        conservative_node_id=None,
                        high_upside_node_id=None,
                        rejected_but_insightful_ids=[],
                        summary_markdown="Missing node.",
                        next_experiments=["Fix the reference."],
                        assumptions=[],
                        failure_modes=[],
                        reversal_conditions=[],
                    ),
                )

    def test_save_snapshot_removes_stale_optional_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020458Z",
            )
            state_with_attachments = _sample_search_state(problem_spec)
            store.save_snapshot(
                manifest.run_id,
                state=state_with_attachments,
                final_recommendation=_sample_final_recommendation(),
                summary_markdown="Initial summary.",
                status=RunStatus.RUNNING,
            )

            stripped_state = _sample_search_state(problem_spec, include_attachments=False)
            store.save_snapshot(
                manifest.run_id,
                state=stripped_state,
                final_recommendation=None,
                summary_markdown=None,
                status=RunStatus.RUNNING,
            )

            run_dir = store.root_dir / manifest.run_id
            self.assertFalse((run_dir / "scores" / "node-0001.json").exists())
            self.assertFalse((run_dir / "critiques" / "node-0001.json").exists())
            self.assertFalse((run_dir / "final-recommendation.json").exists())
            self.assertFalse((run_dir / "summary.md").exists())

            loaded = store.load_run(manifest.run_id)

        self.assertEqual(loaded.state, stripped_state)
        self.assertIsNone(loaded.final_recommendation)
        self.assertIsNone(loaded.summary_markdown)

    def test_store_persists_run_routing_summary_and_merges_aggregate_stats(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            state = _sample_search_state(problem_spec)
            routing_summary = ProviderRoutingStats(
                entries=[
                    ProviderRoutingStatsEntry(
                        provider_name="codex",
                        action_name="generate_seed",
                        run_count=1,
                        invocation_count=1,
                        provider_failure_count=0,
                        candidate_count=2,
                        scored_node_count=2,
                        admitted_count=2,
                        rejected_count=0,
                        hard_fail_count=0,
                        strong_score_count=1,
                        stress_test_survivor_count=1,
                        winner_count=1,
                        winner_contribution_count=1,
                        critique_count=0,
                        useful_critique_count=0,
                        learning_note_count=0,
                        accumulated_score=11.34,
                        total_reward=6.0,
                        last_run_id="run-20260306T020459Z",
                        last_updated_at=datetime(2026, 3, 6, 2, 10, 0, tzinfo=timezone.utc),
                    )
                ],
                updated_at=datetime(2026, 3, 6, 2, 10, 0, tzinfo=timezone.utc),
            )
            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020459Z",
            )

            store.save_snapshot(
                manifest.run_id,
                state=state,
                routing_summary=routing_summary,
                status=RunStatus.RUNNING,
            )
            aggregate = store.merge_provider_routing_stats(routing_summary)
            loaded = store.load_run(manifest.run_id)

        self.assertEqual(loaded.routing_summary, routing_summary)
        self.assertEqual(aggregate, routing_summary)

    def test_store_persists_run_reusable_learning_context(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020500Z",
            )
            memory = LearningMemory.empty().merge_observations(
                run_id="run-prior",
                problem_spec=problem_spec,
                notes=[
                    LearningNote(
                        note_type=LearningNoteType.WINNING_PATTERN,
                        text="Workflow-native ideas beat generic chat loops.",
                        source_node_ids=["node-0009"],
                    )
                ],
                observed_at=datetime(2026, 3, 6, 2, 15, 0, tzinfo=timezone.utc),
            )

            refreshed_manifest = store.save_reusable_learning_context(
                manifest.run_id,
                memory,
                updated_at=manifest.created_at,
            )
            loaded = store.load_run(manifest.run_id)

        self.assertEqual(
            refreshed_manifest.reusable_learning_path,
            "reusable-learning-context.json",
        )
        self.assertEqual(loaded.reusable_learning_context, memory)

    def test_merge_learning_memory_persists_cross_run_observations(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            store.merge_learning_memory(
                run_id="run-20260306T020501Z",
                problem_spec=problem_spec,
                notes=[
                    LearningNote(
                        note_type=LearningNoteType.WINNING_PATTERN,
                        text="Workflow-native ideas beat generic chat loops.",
                        source_node_ids=["node-0001"],
                    )
                ],
                updated_at=datetime(2026, 3, 6, 2, 20, 0, tzinfo=timezone.utc),
            )
            second = store.merge_learning_memory(
                run_id="run-20260306T020502Z",
                problem_spec=problem_spec,
                notes=[
                    LearningNote(
                        note_type=LearningNoteType.WINNING_PATTERN,
                        text="Workflow-native ideas beat generic chat loops.",
                        source_node_ids=["node-0002"],
                    )
                ],
                updated_at=datetime(2026, 3, 6, 2, 25, 0, tzinfo=timezone.utc),
            )
            loaded = store.load_learning_memory()

        self.assertEqual(second, loaded)
        self.assertEqual(len(loaded.entries), 1)
        entry = loaded.entries[0]
        self.assertEqual(entry.observation_count, 2)
        self.assertEqual(entry.source_run_ids, ["run-20260306T020501Z", "run-20260306T020502Z"])
        self.assertEqual(entry.last_seen_at, datetime(2026, 3, 6, 2, 25, 0, tzinfo=timezone.utc))

    def test_record_outcome_feedback_persists_run_and_global_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            state = _sample_search_state(problem_spec)
            manifest = store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-20260306T020503Z",
            )
            store.save_snapshot(
                manifest.run_id,
                state=state,
                final_recommendation=_sample_final_recommendation(),
                summary_markdown="Prefer the workflow-native bet.",
                status=RunStatus.COMPLETED,
            )
            feedback = OutcomeFeedback(
                feedback_id="feedback-20260306T023000Z",
                run_id=manifest.run_id,
                node_id="node-0002",
                candidate_thesis=state.nodes["node-0002"].candidate.thesis,
                problem_statement=problem_spec.request,
                outcome_status=OutcomeFeedbackStatus.VALIDATED,
                summary="Teams stuck with the workflow because weekly review prep became faster.",
                learning_notes=[
                    LearningNote(
                        note_type=LearningNoteType.WINNING_PATTERN,
                        text="Teams will accept setup work when the audit trail saves recurring review time.",
                        source_node_ids=["node-0002"],
                    )
                ],
                evidence=["Pilot teams completed three weekly reviews without churn."],
                experiment_label="weekly-review-pilot",
                recorded_at=datetime(2026, 3, 6, 2, 30, 0, tzinfo=timezone.utc),
            )

            refreshed_manifest, aggregate_feedback, merged_memory = store.record_outcome_feedback(
                feedback
            )
            loaded = store.load_run(manifest.run_id)
            aggregate_routing = store.load_provider_routing_stats()
            run_dir = store.root_dir / manifest.run_id
            run_feedback_exists = (run_dir / "outcome-feedback.json").is_file()
            aggregate_feedback_exists = (
                store.root_dir / "outcome-feedback-ledger.json"
            ).is_file()

        self.assertEqual(refreshed_manifest.outcome_feedback_path, "outcome-feedback.json")
        self.assertTrue(run_feedback_exists)
        self.assertTrue(aggregate_feedback_exists)
        self.assertEqual(len(aggregate_feedback.entries), 1)
        self.assertIsNotNone(loaded.outcome_feedback)
        self.assertEqual(loaded.outcome_feedback.entries[0], feedback)
        self.assertEqual(len(merged_memory.entries), 1)
        self.assertEqual(
            merged_memory.entries[0].evidence_sources,
            [LearningEvidenceSource.OUTCOME_FEEDBACK],
        )
        self.assertIsNotNone(loaded.routing_summary)
        routing_entries = {
            (entry.provider_name, entry.action_name): entry
            for entry in aggregate_routing.entries
        }
        self.assertEqual(routing_entries[("codex", "deepen")].total_reward, 1.0)
        self.assertEqual(
            routing_entries[("opencode", "evaluate_candidate")].total_reward,
            1.0,
        )
        self.assertEqual(
            routing_entries[("gemini", "assess_novelty")].total_reward,
            1.0,
        )

    def test_list_runs_returns_sorted_run_manifests(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            problem_spec = _sample_problem_spec()
            store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-b",
            )
            store.create_run(
                problem_spec=problem_spec,
                provider_name="codex",
                budget=12,
                run_id="run-a",
            )

            manifests = store.list_runs()

        self.assertEqual([manifest.run_id for manifest in manifests], ["run-a", "run-b"])

    def test_load_progress_events_respects_recent_limit(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")
            manifest = store.create_run(
                problem_spec=_sample_problem_spec(),
                provider_name="codex",
                budget=12,
                run_id="run-progress",
            )
            events_path = store.progress_events_path(manifest.run_id)
            events_path.write_text(
                "\n".join(
                    [
                        '{"kind":"run_started","run_id":"run-progress","timestamp":"2026-03-06T00:00:01Z","step_count":0,"budget_spent":0,"payload":{}}',
                        '{"kind":"node_admitted","run_id":"run-progress","timestamp":"2026-03-06T00:00:02Z","step_count":1,"budget_spent":1,"payload":{"node_id":"node-0001"}}',
                        '{"kind":"node_rejected","run_id":"run-progress","timestamp":"2026-03-06T00:00:03Z","step_count":2,"budget_spent":2,"payload":{"node_id":"node-0002"}}',
                        '{"kind":"run_completed","run_id":"run-progress","timestamp":"2026-03-06T00:00:04Z","step_count":3,"budget_spent":3,"payload":{"best_bet":"node-0001"}}',
                    ]
                ),
                encoding="utf-8",
            )

            loaded = store.load_progress_events("run-progress")
            limited = store.load_progress_events("run-progress", limit=2)

        self.assertEqual(len(loaded), 4)
        self.assertEqual(
            [event["kind"] for event in limited],
            ["node_rejected", "run_completed"],
        )

    def test_create_run_rejects_non_finite_metadata_values(self) -> None:
        with TemporaryDirectory() as directory:
            store = FileSystemStateStore(Path(directory) / "artifacts" / "runs")

            with self.assertRaises(ArgusValidationError):
                store.create_run(
                    problem_spec=_sample_problem_spec(),
                    provider_name="codex",
                    budget=12,
                    run_id="run-non-finite-metadata",
                    metadata={"bad_float": float("nan")},
                )


def _sample_problem_spec() -> ProblemSpec:
    return ProblemSpec(
        request="Find the best retention strategy.",
        constraints=["Stay self-serve.", "Preserve auditability."],
        success_criteria=["Increase activation.", "Keep the workflow reproducible."],
        context={"team": "growth"},
    )


def _sample_search_state(
    problem_spec: ProblemSpec,
    *,
    include_attachments: bool = True,
) -> SearchState:
    root_node = Node(
        node_id="node-0001",
        parent_ids=[],
        depth=0,
        action_type=ActionType.FRAME_PROBLEM,
        provider_name="codex",
        candidate=_sample_candidate("Frame the search around workflow lock-in."),
        island_id="balanced",
        score=_sample_score() if include_attachments else None,
        critique=_sample_critique() if include_attachments else None,
        novelty_score=0.63,
        lifecycle_status=NodeLifecycleStatus.ADMITTED,
        metadata={"step": 1},
        created_at=datetime(2026, 3, 6, 2, 4, 56, tzinfo=timezone.utc),
    )
    survivor_node = Node(
        node_id="node-0002",
        parent_ids=["node-0001"],
        depth=1,
        action_type=ActionType.DEEPEN,
        provider_name="codex",
        candidate=_sample_candidate("Bias the product toward team habits, not dashboards."),
        island_id="balanced",
        novelty_score=0.72,
        lifecycle_status=NodeLifecycleStatus.ARCHIVED,
        metadata={
            "step": 2,
            "provider_routing": {
                "assess_novelty": ["gemini"],
                "evaluate_candidate": ["opencode"],
            },
        },
        created_at=datetime(2026, 3, 6, 2, 10, 0, tzinfo=timezone.utc),
    )
    return SearchState(
        problem_spec=problem_spec,
        root_id="node-0001",
        nodes={
            "node-0001": root_node,
            "node-0002": survivor_node,
        },
        archive_ids=["node-0001", "node-0002"],
        frontier_ids=["node-0002"],
        pruned_ids=[],
        winner_ids=["node-0002"],
        islands={
            "balanced": SearchIsland(
                island_id="balanced",
                label="Balanced",
                description="Balanced exploration.",
                archive_ids=["node-0001", "node-0002"],
                frontier_ids=["node-0002"],
                pruned_ids=[],
            )
        },
        learning_notes=[
            LearningNote(
                note_type=LearningNoteType.WINNING_PATTERN,
                text="Workflow-native ideas beat generic engagement loops.",
                source_node_ids=["node-0001", "node-0002"],
            )
        ],
        budget_spent=2,
        step_count=2,
    )


def _sample_candidate(thesis: str) -> Candidate:
    return Candidate(
        thesis=thesis,
        mechanism="Tie the product to repeated operational rituals.",
        assumptions=["Users value lower coordination overhead."],
        strengths=["Creates a durable habit."],
        failure_modes=["Could increase onboarding friction."],
        unknowns=["How much setup work users will tolerate."],
        implementation_shape="Deterministic scoring plus persisted run state.",
        evidence=["The spec requires evaluator-first logic and replayable runs."],
    )


def _sample_score() -> ScoreVector:
    return ScoreVector(
        hard_constraint_pass=True,
        hard_constraint_reasons=[],
        distinctiveness=0.67,
        usefulness=0.82,
        specificity=0.74,
        plausibility=0.78,
        implementation_tractability=0.79,
        upside=0.71,
        adversarial_robustness=0.69,
        evidence_quality=0.63,
        total_score=5.83,
        confidence_estimate=0.77,
    )


def _sample_critique() -> Critique:
    return Critique(
        hidden_dependencies=["Needs strong artifact inspection to stay debuggable."],
        kill_shots=["Falls apart if runs cannot be replayed from disk."],
        sharp_edges=["Can drift if stale score files survive snapshot updates."],
        summary="Operationally sound once persistence is authoritative.",
    )


def _sample_final_recommendation() -> FinalRecommendation:
    return FinalRecommendation(
        best_bet_node_id="node-0002",
        conservative_node_id="node-0001",
        high_upside_node_id="node-0002",
        rejected_but_insightful_ids=[],
        summary_markdown="Prefer the workflow-native bet.",
        next_experiments=["Interview five current users.", "Prototype the audit trail."],
        assumptions=["Teams prefer lower coordination cost over feature breadth."],
        failure_modes=["Setup friction could limit adoption."],
        reversal_conditions=["If interviews show low willingness to change habits."],
        pairwise_decisions=[
            PairwiseDecisionArtifact(
                selection_label="Best bet",
                objective_name="best_overall",
                objective_description="Choose the strongest overall recommendation.",
                left_node_id="node-0002",
                right_node_id="node-0001",
                winner_node_id="node-0002",
                summary="The workflow-native bet compounds value over time.",
                decisive_advantages=["Creates a stronger durable habit loop."],
                decisive_risks=["Onboarding may be heavier."],
                confidence=0.84,
            )
        ],
    )


def _sample_research_bundle() -> ResearchArtifactBundle:
    frame = SearchSpaceFrame(
        frame_id="frame-001",
        problem_statement="Choose the next default Argus runtime.",
        target_decision="Pick the default research runtime to ship.",
        hard_gates=["Must stay deterministic."],
        soft_criteria=["Decision quality", "Latency"],
        baseline_options=["Keep the adaptive runtime."],
        axes=[
            SearchAxis(
                axis_id="coverage",
                label="Coverage",
                description="Coverage planning mode.",
                options=["implicit frontier", "explicit ledger"],
            ),
            SearchAxis(
                axis_id="authoring",
                label="Authoring",
                description="Artifact depth.",
                options=["summary finish", "decision dossier"],
            ),
        ],
        coverage_plan=["Seed each material family once.", "Red-team surviving families."],
    )
    proposal = ProposalBrief(
        proposal_id="proposal-b",
        cell_id="cell-b",
        title="Coverage-led runtime",
        summary="Use an explicit coverage ledger and typed decision artifacts.",
        candidate=_sample_candidate("Coverage-led research runtime"),
        seed_rationale="Directly closes the main product gap.",
        open_questions=["Can it stay within the standard cost profile?"],
        evidence=["The specs require explicit coverage planning."],
        parent_node_ids=["node-0002"],
    )
    return ResearchArtifactBundle(
        search_space_frame=frame,
        coverage_ledger=CoverageLedger(
            ledger_id="ledger-001",
            frame_id=frame.frame_id,
            cells=[
                SearchCell(
                    cell_id="cell-b",
                    label="Explicit ledger plus decision dossier",
                    axis_assignments={
                        "coverage": "explicit ledger",
                        "authoring": "decision dossier",
                    },
                    hypothesis="Higher authoring cost for stronger decision quality.",
                    coverage_status=CoverageStatus.REDTEAMED,
                    uncertainty=0.22,
                    hard_gate_risk=0.18,
                    evidence_strength=0.84,
                    incumbent_proposal_ids=["proposal-b"],
                    notes=["Current leader."],
                )
            ],
            coverage_summary="The explicit-ledger path is the current leader.",
        ),
        scheduler_decisions=[
            SchedulerDecision(
                decision_id="schedule-001",
                action=ResearchSchedulerAction.REDTEAM,
                rationale="Attack the current leader because latency risk is still material.",
                remaining_budget=2,
                priority_score=0.61,
                target_proposal_ids=["proposal-b"],
                signals=[
                    "proposal-b via cell-b: uncertainty=0.22 hard_gate_risk=0.18 evidence_strength=0.84"
                ],
                selected_at=datetime(2026, 3, 8, 18, 44, 0, tzinfo=timezone.utc),
            )
        ],
        proposal_briefs=[proposal],
        triage_reports=[
            TriageReport(
                report_id="triage-001",
                frame_id=frame.frame_id,
                decisions=[
                    ProposalTriageDecision(
                        proposal_id="proposal-b",
                        disposition=ProposalDisposition.SURVIVE,
                        rationale="Best match for the target runtime.",
                    )
                ],
                survivor_ids=["proposal-b"],
                unexplored_cell_ids=[],
                summary="The coverage-led family survives.",
            )
        ],
        deep_dive_docs=[
            DeepDiveDoc(
                doc_id="deep-001",
                proposal_id="proposal-b",
                title="Coverage-led runtime design",
                executive_summary="Separate scheduling from authoring and persist both.",
                detailed_mechanism="Maintain a coverage ledger and write a final decision from the full bundle.",
                implementation_plan=["Persist the bundle.", "Benchmark it against the adaptive control path."],
                key_unknowns=["Latency under the standard cost profile."],
                supporting_evidence=["The specs require typed artifacts."],
                assumptions=["Provider-backed evaluation remains the main judge layer."],
            )
        ],
        adversarial_reviews=[
            AdversarialReview(
                review_id="review-001",
                proposal_id="proposal-b",
                thesis_under_test=proposal.candidate.thesis,
                hidden_dependencies=["The bundle must remain easy to replay."],
                failure_modes=["The richer authoring path could add too much latency."],
                mitigations=["Keep provider dispatch bounded and deterministic."],
                summary="Viable if persistence and latency stay disciplined.",
                verdict="Proceed with explicit latency checks.",
                confidence=0.74,
                evidence=["The runtime already supports deterministic state commits."],
            )
        ],
        comparison_matrices=[
            ComparisonMatrix(
                matrix_id="matrix-001",
                frame_id=frame.frame_id,
                criteria=["decision_quality", "latency"],
                rows=[
                    ComparisonMatrixRow(
                        proposal_id="proposal-b",
                        criterion_scores={"decision_quality": 0.9, "latency": 0.58},
                        advantages=["Best decision package."],
                        liabilities=["Adds more authoring work."],
                        takeaway="Best default if latency stays bounded.",
                    )
                ],
                summary="The explicit-ledger path wins on decision quality.",
            )
        ],
        hybrid_assessments=[],
        final_decision_doc=FinalDecisionDoc(
            decision_id="decision-001",
            frame_id=frame.frame_id,
            selected_proposal_id="proposal-b",
            runner_up_proposal_id=None,
            conservative_proposal_id="proposal-b",
            high_upside_proposal_id="proposal-b",
            summary="Ship the coverage-led runtime.",
            decision_rule="Prefer the option that most improves decision quality without breaking determinism.",
            assumptions=["Artifact persistence stays inspectable."],
            top_risks=["Authoring latency could grow too high."],
            mitigations=["Measure and cap stage concurrency."],
            first_spike=["Persist the research bundle under each run."],
            kill_criteria=["If the richer bundle breaks replay or verification."],
            next_experiments=["Benchmark the research runtime."],
            reversal_conditions=["If decision quality does not improve materially."],
            rejected_proposal_ids=[],
        ),
        decision_summary_markdown="# Argus Recommendation\n\nShip the coverage-led runtime.\n",
        decision_report_markdown="# Final Decision Memo\n\nThe coverage-led runtime should ship next.\n",
    )
