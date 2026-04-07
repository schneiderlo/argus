from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from argus.errors import ArgusValidationError
from argus.models import (
    ActionType,
    Candidate,
    CoverageLedger,
    CoverageStatus,
    HybridVerdict,
    LearningNote,
    LearningNoteType,
    NodeLifecycleStatus,
    ProblemSpec,
    ProposalBrief,
    ProposalDisposition,
    ProposalTriageDecision,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    SearchCell,
    TriageReport,
)
from argus.search.contracts import HybridCandidateBatch, HybridCandidateDecision
from argus.search import (
    ResearchRuntime,
    SearchPolicy,
    SearchRuntime,
    StagedResearchRuntime,
    balanced_island_policy,
    cost_profile_names,
    conservative_island_policy,
    default_search_profile_for_cost_profile,
    search_policy_for_cost_profile,
    search_profile_names,
    upside_island_policy,
)
from argus.search.runtime import _ActionRouter
from argus.storage import FileSystemStateStore, RunStatus
from tests.search_fixtures import (
    SearchFixtureProvider,
    _benchmark_market_candidate,
    _operational_assistant_candidate,
    _workflow_archive_candidate,
)


class CoverageAwareResearchFixtureProvider(SearchFixtureProvider):
    def _handle_seed_cell_proposals(
        self,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
    ):
        proposals = super()._handle_seed_cell_proposals(problem_spec, input_payload)
        target_cell_ids = {
            str(cell_payload["cell_id"])
            for cell_payload in list(input_payload.get("target_cells", []))
        }
        if target_cell_ids == {"cell-control"}:
            return type(proposals)(
                proposals=[
                    ProposalBrief(
                        proposal_id="proposal-control-2",
                        cell_id="cell-control",
                        title="Adaptive control path with explicit coverage checkpoint",
                        summary="Reseed the control cell with a stronger representative before deepening the leader.",
                        candidate=Candidate(
                            thesis="Adaptive control path with explicit coverage checkpoint",
                            mechanism=(
                                "Keep the adaptive loop, but add an explicit coverage checkpoint before final decision writing."
                            ),
                            assumptions=["A lighter coverage checkpoint could rescue the control family."],
                            strengths=["Lower migration cost than the full coverage-led runtime."],
                            failure_modes=["Still weaker than a true ledger-driven scheduler."],
                            unknowns=["Whether the checkpoint materially improves operator trust."],
                            implementation_shape="Adaptive runtime plus one explicit coverage review stage.",
                            evidence=["Useful as a stronger control family for direct comparison."],
                        ),
                        seed_rationale="The first control proposal was too weak, so the scheduler should reseed the uncovered family once.",
                        open_questions=["Can this lighter checkpoint close enough of the audit gap?"],
                        evidence=["The scheduler kept the family open because the cell was still high-value."],
                        parent_node_ids=list(input_payload.get("parent_node_ids", [])),
                    )
                ],
                batch_summary="Reseeded the still-interesting control family with a stronger representative.",
            )
        return proposals

    def _handle_triage_proposals(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> TriageReport:
        proposals = list(input_payload["proposals"])
        proposal_ids = [str(proposal["proposal_id"]) for proposal in proposals]
        if "proposal-control-2" not in proposal_ids:
            return TriageReport(
                report_id="triage-coverage-001",
                frame_id=str(input_payload["frame_id"]),
                decisions=[
                    ProposalTriageDecision(
                        proposal_id="proposal-control",
                        disposition=ProposalDisposition.ELIMINATE,
                        rationale="The first control representative is too weak, but the family is still strategically relevant.",
                        follow_up="Reseed the control family with a stronger representative.",
                    ),
                    ProposalTriageDecision(
                        proposal_id="proposal-ledger",
                        disposition=ProposalDisposition.SURVIVE,
                        rationale="Still the strongest family overall.",
                        follow_up="Keep it alive, but do not deepen yet while an uncovered high-value cell remains.",
                    ),
                ],
                survivor_ids=["proposal-ledger"],
                unexplored_cell_ids=["cell-control"],
                summary="Keep the ledger leader alive, but expand the still-important control family before deepening.",
                next_actions=["Reseed the control family before spending more depth budget on the incumbent."],
            )

        return TriageReport(
            report_id="triage-coverage-002",
            frame_id=str(input_payload["frame_id"]),
            decisions=[
                ProposalTriageDecision(
                    proposal_id="proposal-control",
                    disposition=ProposalDisposition.ELIMINATE,
                    rationale="Superseded by the stronger reseeded control representative.",
                    follow_up="Retain only the stronger control variant.",
                ),
                ProposalTriageDecision(
                    proposal_id="proposal-control-2",
                    disposition=ProposalDisposition.SURVIVE,
                    rationale="Strong enough to compare directly against the ledger-driven option.",
                    follow_up="Deepen it alongside the current leader.",
                ),
                ProposalTriageDecision(
                    proposal_id="proposal-ledger",
                    disposition=ProposalDisposition.SURVIVE,
                    rationale="Remains the leading family after the control reseed.",
                    follow_up="Deepen it now that coverage is materially complete.",
                ),
            ],
            survivor_ids=["proposal-control-2", "proposal-ledger"],
            unexplored_cell_ids=[],
            summary="Coverage is now good enough to deepen the surviving families.",
            next_actions=["Deepen both surviving families before the final decision."],
        )


class RejectingHybridFixtureProvider(SearchFixtureProvider):
    def _handle_combine(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> HybridCandidateBatch:
        primary = Candidate.from_dict(input_payload["primary_candidate"])
        secondary = Candidate.from_dict(input_payload["secondary_candidate"])
        return HybridCandidateBatch(
            decisions=[
                HybridCandidateDecision(
                    hybrid_name="Kitchen-sink retention mashup",
                    seam_hypothesis="The two ideas would need a larger product surface instead of one clean seam.",
                    repaired_failure_mode="Neither candidate's main weakness is actually repaired by bolting them together.",
                    complementary_strengths=[
                        primary.strengths[0],
                        secondary.strengths[0],
                    ],
                    complexity_tax="Would force the product to ship two partially connected mechanisms at once.",
                    expected_upside="Only superficial breadth, not a cleaner winning mechanism.",
                    open_questions=["Which mechanism would the operator actually lead with?"],
                    verdict=HybridVerdict.REJECT,
                    summary="Reject the hybrid because the seam is vague and the complexity tax overwhelms the upside.",
                )
            ],
            batch_summary="Rejected the attempted hybrid because it never cleared the seam gate.",
        )


class RepairingFinalDecisionFixtureProvider(SearchFixtureProvider):
    def _handle_write_final_decision(
        self,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
    ):
        if "schema_repair_feedback" in input_payload:
            return super()._handle_write_final_decision(problem_spec, input_payload)
        invalid_payload = super()._handle_write_final_decision(problem_spec, input_payload).to_dict()
        invalid_payload["comparison_matrix"]["rows"] = [
            row
            for row in invalid_payload["comparison_matrix"]["rows"]
            if row["proposal_id"] != "proposal-control"
        ]
        return invalid_payload


class UnknownProposalIdFinalDecisionFixtureProvider(SearchFixtureProvider):
    def _handle_write_final_decision(
        self,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
    ):
        if "schema_repair_feedback" in input_payload:
            return super()._handle_write_final_decision(problem_spec, input_payload)
        invalid_payload = super()._handle_write_final_decision(problem_spec, input_payload).to_dict()
        for row in invalid_payload["comparison_matrix"]["rows"]:
            if row["proposal_id"] == "proposal-ledger":
                row["proposal_id"] = "coverage-led-runtime"
        invalid_payload["final_decision_doc"]["selected_proposal_id"] = "coverage-led-runtime"
        invalid_payload["final_decision_doc"]["high_upside_proposal_id"] = "coverage-led-runtime"
        return invalid_payload


class SearchRuntimeTests(unittest.TestCase):
    def test_hybrid_candidate_decision_requires_candidate_only_for_pursued_hybrids(self) -> None:
        with self.assertRaises(ArgusValidationError):
            HybridCandidateDecision(
                hybrid_name="Unsupported hybrid",
                seam_hypothesis="The seam is unclear.",
                repaired_failure_mode="No real failure mode is repaired.",
                complementary_strengths=["More breadth."],
                complexity_tax="Adds surface area without focus.",
                expected_upside="Only superficial upside.",
                open_questions=["Why combine these at all?"],
                verdict=HybridVerdict.PURSUE,
                summary="Should fail because candidate is missing.",
                candidate=None,
            )

        with self.assertRaises(ArgusValidationError):
            HybridCandidateDecision(
                hybrid_name="Rejected hybrid carrying a candidate",
                seam_hypothesis="The seam exists only on paper.",
                repaired_failure_mode="Still does not repair the actual weakness.",
                complementary_strengths=["Looks broader."],
                complexity_tax="Ships too many ideas at once.",
                expected_upside="Weak and speculative.",
                open_questions=["Which piece matters most?"],
                verdict=HybridVerdict.REJECT,
                summary="Should fail because rejected hybrids must not return a candidate.",
                candidate=_workflow_archive_candidate(),
            )

    def test_action_router_uses_ucb_to_explore_under_sampled_provider(self) -> None:
        codex_provider = SearchFixtureProvider(Path("/tmp/argus-router-codex"), name="codex")
        gemini_provider = SearchFixtureProvider(Path("/tmp/argus-router-gemini"), name="gemini")
        router = _ActionRouter(
            providers={
                "codex": codex_provider,
                "gemini": gemini_provider,
            },
            default_provider_name="codex",
            routing_stats=ProviderRoutingStats(
                entries=[
                    ProviderRoutingStatsEntry(
                        provider_name="codex",
                        action_name="evaluate_candidate",
                        run_count=5,
                        invocation_count=20,
                        provider_failure_count=0,
                        candidate_count=20,
                        scored_node_count=20,
                        admitted_count=14,
                        rejected_count=3,
                        hard_fail_count=3,
                        strong_score_count=10,
                        stress_test_survivor_count=8,
                        winner_count=3,
                        winner_contribution_count=5,
                        critique_count=0,
                        useful_critique_count=0,
                        learning_note_count=0,
                        accumulated_score=120.0,
                        total_reward=18.0,
                        last_run_id="run-router-codex",
                        last_updated_at=datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc),
                    ),
                    ProviderRoutingStatsEntry(
                        provider_name="gemini",
                        action_name="evaluate_candidate",
                        run_count=1,
                        invocation_count=3,
                        provider_failure_count=0,
                        candidate_count=3,
                        scored_node_count=3,
                        admitted_count=2,
                        rejected_count=0,
                        hard_fail_count=1,
                        strong_score_count=1,
                        stress_test_survivor_count=1,
                        winner_count=1,
                        winner_contribution_count=1,
                        critique_count=0,
                        useful_critique_count=0,
                        learning_note_count=0,
                        accumulated_score=18.0,
                        total_reward=2.4,
                        last_run_id="run-router-gemini",
                        last_updated_at=datetime(2026, 3, 7, 12, 5, 0, tzinfo=timezone.utc),
                    ),
                ],
                updated_at=datetime(2026, 3, 7, 12, 5, 0, tzinfo=timezone.utc),
            ),
        )

        selected = router.select("evaluate_candidate")

        self.assertEqual(selected.name, "gemini")

    def test_cost_profiles_map_to_expected_search_policies(self) -> None:
        self.assertEqual(cost_profile_names(), ("lean", "standard", "max"))
        self.assertEqual(search_profile_names(), ("balanced", "portfolio"))
        self.assertEqual(default_search_profile_for_cost_profile("lean"), "balanced")
        self.assertEqual(default_search_profile_for_cost_profile("standard"), "portfolio")
        self.assertEqual(default_search_profile_for_cost_profile("max"), "portfolio")

        lean = search_policy_for_cost_profile("lean")
        standard = search_policy_for_cost_profile("standard")
        max_profile = search_policy_for_cost_profile("max")
        balanced_standard = search_policy_for_cost_profile(
            "standard",
            search_profile="balanced",
        )

        self.assertEqual(lean.seed_target, 4)
        self.assertEqual(lean.stress_test_limit, 2)
        self.assertEqual(lean.frontier_limit, 4)
        self.assertEqual(lean.provider_max_concurrency, 2)
        self.assertEqual([policy.island_id for policy in lean.island_policies], ["balanced"])

        self.assertEqual(
            [policy.island_id for policy in standard.island_policies],
            ["balanced", "conservative", "upside"],
        )
        self.assertEqual(
            [policy.island_id for policy in balanced_standard.island_policies],
            ["balanced"],
        )

        self.assertEqual(max_profile.seed_target, 12)
        self.assertEqual(max_profile.stress_test_limit, 6)
        self.assertEqual(max_profile.combine_limit, 2)
        self.assertEqual(max_profile.frontier_limit, 8)
        self.assertEqual(max_profile.provider_max_concurrency, 8)
        self.assertEqual(
            [policy.island_id for policy in max_profile.island_policies],
            ["balanced", "conservative", "upside"],
        )

        with self.assertRaises(ArgusValidationError):
            search_policy_for_cost_profile("tiny")
        with self.assertRaises(ArgusValidationError):
            search_policy_for_cost_profile("standard", search_profile="unknown")

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
            aggregate_routing = store.load_provider_routing_stats()

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
        self.assertGreaterEqual(action_names.count("rank"), 6)
        self.assertGreaterEqual(action_names.count("evaluate_candidate_batch"), 3)
        self.assertGreaterEqual(action_names.count("assess_novelty_batch"), 3)
        self.assertIsNotNone(loaded.routing_summary)
        self.assertEqual(loaded.routing_summary, aggregate_routing)
        self.assertIn("Pairwise Selection Checks", result.summary_markdown)

        entries = {
            entry.action_name: entry
            for entry in loaded.routing_summary.entries
            if entry.provider_name == provider.name
        }
        self.assertEqual(entries["frame_problem"].winner_contribution_count, 1)
        self.assertEqual(entries["generate_seed"].candidate_count, 4)
        self.assertEqual(entries["generate_seed"].admitted_count, 3)
        self.assertEqual(entries["generate_seed"].hard_fail_count, 1)
        self.assertEqual(entries["generate_seed"].stress_test_survivor_count, 2)
        self.assertEqual(entries["generate_seed"].winner_contribution_count, 3)
        self.assertGreaterEqual(entries["rank"].invocation_count, 6)
        self.assertEqual(entries["stress_test"].critique_count, 2)
        self.assertEqual(entries["stress_test"].useful_critique_count, 2)
        self.assertEqual(entries["deepen"].winner_count, 1)
        self.assertEqual(entries["evaluate_candidate"].candidate_count, len(result.state.nodes))
        self.assertLessEqual(
            entries["evaluate_candidate"].invocation_count,
            entries["evaluate_candidate"].candidate_count,
        )
        self.assertEqual(entries["assess_novelty"].candidate_count, len(result.state.nodes) - 1)
        self.assertLessEqual(
            entries["assess_novelty"].invocation_count,
            entries["assess_novelty"].candidate_count,
        )
        self.assertEqual(entries["compress_learning"].learning_note_count, 2)
        combine_nodes = [
            node
            for node in result.state.nodes.values()
            if node.action_type is ActionType.COMBINE and node.node_id in result.state.archive_ids
        ]
        self.assertEqual(len(combine_nodes), 1)
        self.assertEqual(
            combine_nodes[0].metadata["hybrid_gate"]["repaired_failure_mode"],
            "Peer benchmarks fail when trust and proprietary-data value are not established first.",
        )
        self.assertEqual(
            combine_nodes[0].metadata["hybrid_gate"]["verdict"],
            "pursue",
        )

    def test_research_runtime_persists_bundle_and_final_decision(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            runtime = ResearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    frontier_limit=4,
                    provider_max_concurrency=2,
                ),
            )

            result = runtime.run(
                request="Choose the default research runtime to ship next.",
                budget=7,
                run_id="run-research-fixture",
            )
            loaded = store.load_run("run-research-fixture")
            action_names = [call["action_name"] for call in provider.calls]
            self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
            self.assertIn("frame_search_space", action_names)
            self.assertIn("seed_cell_proposals", action_names)
            self.assertIn("triage_proposals", action_names)
            self.assertIn("deepen_family", action_names)
            self.assertIn("redteam_family", action_names)
            self.assertIn("write_final_decision", action_names)
            self.assertIsNotNone(loaded.research_bundle)
            self.assertEqual(
                [decision.action.value for decision in loaded.research_bundle.scheduler_decisions],
                ["expand", "deepen", "redteam", "stop"],
            )
            self.assertEqual(
                loaded.research_bundle.final_decision_doc.selected_proposal_id,
                "proposal-ledger",
            )
            self.assertIn("Research Decision", loaded.research_bundle.decision_summary_markdown)
            self.assertIn("Final Decision Memo", loaded.research_bundle.decision_report_markdown)
            self.assertEqual(
                result.summary_markdown,
                loaded.research_bundle.decision_summary_markdown,
            )
            self.assertTrue((loaded.path / "research" / "bundle.json").is_file())
            self.assertTrue((loaded.path / "research" / "markdown" / "decision-summary.md").is_file())
            self.assertTrue((loaded.path / "research" / "markdown" / "final-decision.md").is_file())
            self.assertTrue(
                (loaded.path / "research" / "markdown" / "scheduler" / "schedule-001.md").is_file()
            )
            self.assertIn("Research Decision", result.summary_markdown)
            self.assertEqual(result.final_recommendation.best_bet_node_id, "node-0003")

    def test_research_runtime_expands_uncovered_high_value_cell_before_deepening(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = CoverageAwareResearchFixtureProvider(
                root / "artifacts" / "provider_invocations"
            )
            runtime = ResearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    frontier_limit=4,
                    provider_max_concurrency=2,
                ),
            )

            runtime.run(
                request="Choose the default research runtime to ship next.",
                budget=8,
                run_id="run-research-coverage-aware",
            )
            loaded = store.load_run("run-research-coverage-aware")
            action_names = [call["action_name"] for call in provider.calls]
            major_actions = [
                action_name
                for action_name in action_names
                if action_name
                in {
                    "frame_search_space",
                    "seed_cell_proposals",
                    "triage_proposals",
                    "deepen_family",
                    "redteam_family",
                    "assess_hybrid",
                    "write_final_decision",
                }
            ]
            scheduler_actions = [
                decision.action.value
                for decision in loaded.research_bundle.scheduler_decisions
            ]

            self.assertEqual(major_actions[:5], [
                "frame_search_space",
                "seed_cell_proposals",
                "triage_proposals",
                "seed_cell_proposals",
                "triage_proposals",
            ])
            self.assertIn("deepen_family", major_actions[5:])
            self.assertLess(major_actions.index("deepen_family"), major_actions.index("write_final_decision"))
            self.assertEqual(scheduler_actions[:3], ["expand", "expand", "deepen"])
            self.assertEqual(
                loaded.research_bundle.scheduler_decisions[1].target_cell_ids,
                ["cell-control"],
            )
            self.assertNotIn("redteam_family", major_actions[:6])

    def test_research_runtime_keeps_survivor_incumbents_for_cells_marked_for_more_expansion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            runtime = ResearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    frontier_limit=4,
                    provider_max_concurrency=2,
                ),
            )

            control_brief = ProposalBrief(
                proposal_id="proposal-control",
                cell_id="cell-control",
                title="Adaptive control path",
                summary="Keep the lighter control family alive while still expanding the same cell.",
                candidate=Candidate(
                    thesis="Adaptive control path",
                    mechanism="Use a lighter control path as the benchmark family.",
                    assumptions=["The control family is still worth comparing."],
                    strengths=["Low migration cost."],
                    failure_modes=["Can remain too lossy without more evidence."],
                    unknowns=["Whether a sharper control variant is still needed."],
                    implementation_shape="Adaptive runtime with lighter coverage checks.",
                    evidence=["Useful as a benchmark control."],
                ),
                seed_rationale="Keeps the control family represented in the ledger.",
                open_questions=["Should the same cell get another representative?"],
                evidence=["The control family still matters strategically."],
                parent_node_ids=["node-0001"],
            )
            ledger_brief = ProposalBrief(
                proposal_id="proposal-ledger",
                cell_id="cell-ledger",
                title="Coverage-led runtime",
                summary="Keep the ledger-driven family alive as the main survivor.",
                candidate=Candidate(
                    thesis="Coverage-led runtime",
                    mechanism="Frame search space explicitly and deepen survivors.",
                    assumptions=["Coverage-led planning remains the stronger default."],
                    strengths=["Best audit trail."],
                    failure_modes=["Could cost more latency."],
                    unknowns=["How much more evidence is still needed?"],
                    implementation_shape="Typed research bundle with explicit coverage ledger.",
                    evidence=["Matches the main product gap."],
                ),
                seed_rationale="Represents the leading family.",
                open_questions=["How much more depth is still required?"],
                evidence=["Current leader for decision quality."],
                parent_node_ids=["node-0001"],
            )
            ledger = CoverageLedger(
                ledger_id="ledger-mixed-001",
                frame_id="frame-001",
                cells=[
                    SearchCell(
                        cell_id="cell-control",
                        label="Control family",
                        axis_assignments={"coverage": "implicit frontier"},
                        hypothesis="A stronger control representative is still worth comparing.",
                        coverage_status=CoverageStatus.SEEDED,
                        uncertainty=0.48,
                        hard_gate_risk=0.34,
                        evidence_strength=0.52,
                        incumbent_proposal_ids=["proposal-control"],
                        notes=["Representative proposals seeded."],
                    ),
                    SearchCell(
                        cell_id="cell-ledger",
                        label="Ledger family",
                        axis_assignments={"coverage": "explicit ledger"},
                        hypothesis="The ledger-driven family is still the main leader.",
                        coverage_status=CoverageStatus.SEEDED,
                        uncertainty=0.31,
                        hard_gate_risk=0.22,
                        evidence_strength=0.79,
                        incumbent_proposal_ids=["proposal-ledger"],
                        notes=["Representative proposals seeded."],
                    ),
                ],
                coverage_summary="Two families have seeded representatives.",
            )
            triage_report = TriageReport(
                report_id="triage-mixed-001",
                frame_id="frame-001",
                decisions=[
                    ProposalTriageDecision(
                        proposal_id="proposal-control",
                        disposition=ProposalDisposition.SURVIVE,
                        rationale="Keep the control family alive, but expand the same cell again.",
                        follow_up="Reseed the control cell with one sharper representative.",
                    ),
                    ProposalTriageDecision(
                        proposal_id="proposal-ledger",
                        disposition=ProposalDisposition.SURVIVE,
                        rationale="Still the overall leader.",
                        follow_up="Deepen the ledger family once the comparison set is complete.",
                    ),
                ],
                survivor_ids=["proposal-control", "proposal-ledger"],
                unexplored_cell_ids=["cell-control"],
                summary="Keep the control family alive while still expanding that cell.",
                next_actions=["Reseed the control cell before final comparison."],
            )
            proposal_records = {
                "proposal-control": SimpleNamespace(brief=control_brief, node_id="node-control"),
                "proposal-ledger": SimpleNamespace(brief=ledger_brief, node_id="node-ledger"),
            }
            state = SimpleNamespace(
                nodes={
                    "node-control": SimpleNamespace(
                        score=SimpleNamespace(confidence_estimate=0.61),
                    ),
                    "node-ledger": SimpleNamespace(
                        score=SimpleNamespace(confidence_estimate=0.84),
                    ),
                }
            )

            updated_ledger = runtime._update_triaged_ledger(
                ledger=ledger,
                triage_report=triage_report,
                proposal_records=proposal_records,
                state=state,
            )
            cells_by_id = {cell.cell_id: cell for cell in updated_ledger.cells}

            self.assertEqual(
                cells_by_id["cell-control"].incumbent_proposal_ids,
                ["proposal-control"],
            )
            self.assertEqual(
                cells_by_id["cell-control"].coverage_status,
                CoverageStatus.TRIAGED,
            )
            self.assertIn(
                "Cell still warrants more expansion after triage.",
                cells_by_id["cell-control"].notes,
            )
            self.assertEqual(
                [cell.cell_id for cell in runtime._expandable_cells(
                    updated_ledger,
                    latest_triage_report=triage_report,
                    require_value_gate=False,
                )],
                ["cell-control"],
            )
            self.assertIn(
                "proposal-control",
                runtime._pending_deepen_ids(
                    ledger=updated_ledger,
                    survivor_ids=triage_report.survivor_ids,
                    bundle=SimpleNamespace(deep_dive_docs=[]),
                ),
            )

    def test_research_runtime_repairs_final_decision_schema_mismatch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = RepairingFinalDecisionFixtureProvider(
                root / "artifacts" / "provider_invocations"
            )
            runtime = ResearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    frontier_limit=4,
                    provider_max_concurrency=2,
                ),
            )

            result = runtime.run(
                request="Choose the default research runtime to ship next.",
                budget=7,
                run_id="run-research-final-decision-repair",
            )
            loaded = store.load_run("run-research-final-decision-repair")
            decision_calls = [
                call for call in provider.calls if call["action_name"] == "write_final_decision"
            ]

            self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
            self.assertEqual(len(decision_calls), 2)
            self.assertNotIn("schema_repair_feedback", decision_calls[0]["input_payload"])
            repair_feedback = decision_calls[1]["input_payload"]["schema_repair_feedback"]
            self.assertEqual(
                repair_feedback["missing_comparison_matrix_proposal_ids"],
                ["proposal-control"],
            )
            self.assertIn(
                "proposal-control",
                [row.proposal_id for row in loaded.research_bundle.comparison_matrices[0].rows],
            )
            self.assertEqual(
                loaded.research_bundle.final_decision_doc.runner_up_proposal_id,
                "proposal-control",
            )

    def test_research_runtime_repairs_unknown_final_decision_proposal_ids(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = UnknownProposalIdFinalDecisionFixtureProvider(
                root / "artifacts" / "provider_invocations"
            )
            runtime = ResearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    frontier_limit=4,
                    provider_max_concurrency=2,
                ),
            )

            result = runtime.run(
                request="Choose the default research runtime to ship next.",
                budget=7,
                run_id="run-research-final-decision-unknown-id-repair",
            )
            loaded = store.load_run("run-research-final-decision-unknown-id-repair")
            decision_calls = [
                call for call in provider.calls if call["action_name"] == "write_final_decision"
            ]

            self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
            self.assertEqual(len(decision_calls), 2)
            repair_feedback = decision_calls[1]["input_payload"]["schema_repair_feedback"]
            self.assertEqual(
                repair_feedback["unknown_proposal_ids"],
                ["coverage-led-runtime"],
            )
            self.assertEqual(
                repair_feedback["available_proposal_ids"],
                ["proposal-control", "proposal-ledger"],
            )
            self.assertIn(
                "proposal-ledger",
                [row.proposal_id for row in loaded.research_bundle.comparison_matrices[0].rows],
            )

    def test_staged_runtime_runs_fixed_pipeline_without_redteam_or_hybrid(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")
            runtime = StagedResearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    frontier_limit=4,
                    provider_max_concurrency=2,
                ),
            )

            result = runtime.run(
                request="Choose the default research runtime to ship next.",
                budget=6,
                run_id="run-staged-fixture",
            )
            loaded = store.load_run("run-staged-fixture")
            action_names = [call["action_name"] for call in provider.calls]
            self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
            self.assertEqual(
                action_names,
                [
                    "frame_search_space",
                    "evaluate_candidate",
                    "seed_cell_proposals",
                    "assess_novelty_batch",
                    "evaluate_candidate_batch",
                    "assess_novelty",
                    "triage_proposals",
                    "deepen_family",
                    "write_final_decision",
                ],
            )
            self.assertNotIn("redteam_family", action_names)
            self.assertNotIn("assess_hybrid", action_names)
            self.assertIsNotNone(loaded.research_bundle)
            self.assertEqual(loaded.manifest.metadata["runtime_mode"], "staged")
            self.assertIn("Research Decision", result.summary_markdown)

    def test_runtime_default_policy_matches_cli_portfolio_default(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(root / "artifacts" / "provider_invocations")

            runtime = SearchRuntime(provider=provider, state_store=store)

        self.assertEqual(
            [island.island_id for island in runtime.policy.island_policies],
            ["balanced", "conservative", "upside"],
        )

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
            aggregate_routing = store.load_provider_routing_stats()

        self.assertEqual(loaded.manifest.status, RunStatus.FAILED)
        self.assertIsNone(loaded.state)
        self.assertEqual(loaded.manifest.metadata["failed_action"], "frame_problem")
        self.assertEqual(loaded.manifest.metadata["search_profile"], "portfolio")
        self.assertEqual(
            loaded.manifest.metadata["island_ids"],
            ["balanced", "conservative", "upside"],
        )
        self.assertIn("frame_problem", loaded.manifest.error)
        self.assertIsNotNone(loaded.routing_summary)
        self.assertEqual(loaded.routing_summary, aggregate_routing)
        self.assertEqual(len(loaded.routing_summary.entries), 1)
        entry = loaded.routing_summary.entries[0]
        self.assertEqual(entry.action_name, "frame_problem")
        self.assertEqual(entry.invocation_count, 1)
        self.assertEqual(entry.provider_failure_count, 1)
        self.assertEqual(entry.total_reward, -2.0)

    def test_runtime_reuses_and_merges_cross_run_learning_memory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            store.merge_learning_memory(
                run_id="run-prior-learning",
                problem_spec=ProblemSpec(
                    request="Design the best retention strategy for a workflow-heavy product.",
                    constraints=["Keep every decision auditable."],
                    success_criteria=["Increase repeated use."],
                    context={"segment": "product"},
                ),
                notes=[
                    LearningNote(
                        note_type=LearningNoteType.WINNING_PATTERN,
                        text="Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
                        source_node_ids=["node-0003"],
                    )
                ],
            )
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
                    reusable_learning_limit=2,
                ),
            )

            runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=9,
                run_id="run-search-learning-memory",
            )
            loaded = store.load_run("run-search-learning-memory")
            memory = store.load_learning_memory()
            context_path = loaded.path / "reusable-learning-context.json"

        frame_call = next(call for call in provider.calls if call["action_name"] == "frame_problem")
        evaluation_call = next(
            call
            for call in provider.calls
            if call["action_name"] in {"evaluate_candidate", "evaluate_candidate_batch"}
        )
        self.assertIn("reusable_learning_notes", frame_call["input_payload"])
        self.assertEqual(
            frame_call["input_payload"]["reusable_learning_notes"][0]["text"],
            "Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
        )
        self.assertEqual(
            evaluation_call["input_payload"]["reusable_learning_notes"][0]["text"],
            "Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
        )
        self.assertIsNotNone(loaded.reusable_learning_context)
        self.assertEqual(len(loaded.reusable_learning_context.entries), 1)
        self.assertEqual(loaded.manifest.reusable_learning_path, "reusable-learning-context.json")
        self.assertTrue(str(context_path).endswith("reusable-learning-context.json"))
        entry = next(
            item
            for item in memory.entries
            if item.text == "Workflow-native, auditable mechanisms outperform generic chat-shaped ideas."
        )
        self.assertEqual(entry.observation_count, 2)
        self.assertEqual(
            entry.source_run_ids,
            ["run-prior-learning", "run-search-learning-memory"],
        )

    def test_runtime_uses_bounded_concurrency_for_independent_provider_calls(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations",
                sleep_by_action={
                    "assess_novelty": 0.03,
                    "assess_novelty_batch": 0.03,
                    "evaluate_candidate": 0.03,
                    "evaluate_candidate_batch": 0.03,
                    "stress_test": 0.03,
                    "deepen": 0.03,
                },
            )
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
                    provider_max_concurrency=2,
                ),
            )

            runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=9,
                run_id="run-search-concurrency",
            )

        self.assertLessEqual(_max_overlap(provider.calls), 2)
        self.assertGreaterEqual(
            sum(
                1
                for call in provider.calls
                if call["action_name"] in {"assess_novelty_batch", "evaluate_candidate_batch"}
            ),
            2,
        )
        self.assertEqual(_max_overlap(provider.calls, actions={"stress_test"}), 2)
        self.assertEqual(_max_overlap(provider.calls, actions={"deepen"}), 2)

    def test_runtime_reopens_seed_generation_when_frontier_width_collapses(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations",
                seed_candidates=[_workflow_archive_candidate()],
            )
            runtime = SearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    seed_target=4,
                    stress_test_limit=1,
                    deepen_limit=1,
                    mutate_limit=1,
                    combine_limit=1,
                    frontier_limit=3,
                    rejected_limit=2,
                    max_learning_notes=1,
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=6,
                run_id="run-search-seed-reopen",
            )

        generate_calls = [
            call for call in provider.calls if call["action_name"] == "generate_seed"
        ]
        self.assertGreaterEqual(len(generate_calls), 2)
        self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
        self.assertTrue(result.state.archive_ids)

    def test_runtime_rejects_hybrids_that_fail_the_combine_gate(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = RejectingHybridFixtureProvider(
                root / "artifacts" / "provider_invocations"
            )
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
                run_id="run-search-hybrid-gate",
            )

        combine_calls = [call for call in provider.calls if call["action_name"] == "combine"]
        combine_nodes = [
            node for node in result.state.nodes.values() if node.action_type is ActionType.COMBINE
        ]

        self.assertEqual(len(combine_calls), 1)
        self.assertEqual(combine_nodes, [])
        self.assertTrue(result.final_recommendation.best_bet_node_id in result.state.archive_ids)

    def test_runtime_revisits_archive_parents_when_stage_budget_exceeds_frontier(self) -> None:
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
                    deepen_limit=1,
                    mutate_limit=1,
                    combine_limit=1,
                    frontier_limit=1,
                    rejected_limit=2,
                    max_learning_notes=1,
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=4,
                run_id="run-search-archive-revisit",
            )

        stress_calls = [call for call in provider.calls if call["action_name"] == "stress_test"]
        stressed_node_ids = [str(call["input_payload"]["node_id"]) for call in stress_calls]

        self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
        self.assertEqual(len(stress_calls), 2)
        self.assertEqual(len(result.state.frontier_ids), 1)
        self.assertEqual(len(set(stressed_node_ids)), 2)
        self.assertTrue(all(node_id in result.state.archive_ids for node_id in stressed_node_ids))
        self.assertTrue(
            any(node_id not in result.state.frontier_ids for node_id in stressed_node_ids)
        )

    def test_runtime_rejects_same_batch_duplicates_after_parallel_archive_checks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            duplicate_candidate = _workflow_archive_candidate()
            provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations",
                sleep_by_action={
                    "assess_novelty": 0.02,
                    "assess_novelty_batch": 0.02,
                    "evaluate_candidate": 0.02,
                    "evaluate_candidate_batch": 0.02,
                },
                seed_candidates=[
                    duplicate_candidate,
                    duplicate_candidate,
                    _operational_assistant_candidate(),
                    _benchmark_market_candidate(),
                ],
            )
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
                    provider_max_concurrency=4,
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=9,
                run_id="run-search-intra-batch-dedupe",
            )

        duplicate_seed_nodes = [
            node
            for node in result.state.nodes.values()
            if node.action_type is ActionType.GENERATE_SEED
            and node.candidate.thesis == "Workflow-native decision archive"
        ]
        admitted_duplicates = [
            node for node in duplicate_seed_nodes if node.node_id in result.state.archive_ids
        ]
        rejected_duplicates = [
            node
            for node in duplicate_seed_nodes
            if node.lifecycle_status is NodeLifecycleStatus.REJECTED
        ]

        self.assertEqual(len(duplicate_seed_nodes), 2)
        self.assertEqual(len(admitted_duplicates), 1)
        self.assertEqual(len(rejected_duplicates), 1)
        self.assertEqual(
            rejected_duplicates[0].metadata["novelty"]["nearest_neighbor_id"],
            admitted_duplicates[0].node_id,
        )
        self.assertIn(
            "near-duplicate",
            rejected_duplicates[0].metadata["novelty"]["summary"].lower(),
        )

    def test_runtime_supports_multi_island_search_with_independent_frontiers(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations",
                seed_candidates_by_island={
                    "balanced": [_workflow_archive_candidate()],
                    "conservative": [_operational_assistant_candidate()],
                    "upside": [_benchmark_market_candidate()],
                },
            )
            runtime = SearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    seed_target=3,
                    stress_test_limit=3,
                    deepen_limit=3,
                    mutate_limit=1,
                    combine_limit=1,
                    frontier_limit=6,
                    rejected_limit=2,
                    max_learning_notes=2,
                    island_policies=(
                        balanced_island_policy(),
                        conservative_island_policy(),
                        upside_island_policy(),
                    ),
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=12,
                run_id="run-search-multi-island",
            )

        self.assertEqual(
            list(result.state.islands),
            ["balanced", "conservative", "upside"],
        )
        for island_id, island in result.state.islands.items():
            self.assertIn(result.state.root_id, island.archive_ids)
            self.assertGreaterEqual(len(island.archive_ids), 2)
            self.assertGreaterEqual(len(island.frontier_ids), 1)
        for node in result.state.nodes.values():
            if node.node_id == result.state.root_id:
                self.assertIsNone(node.island_id)
                continue
            self.assertIn(node.island_id, result.state.islands)
            for parent_id in node.parent_ids:
                parent = result.state.nodes[parent_id]
                if parent_id == result.state.root_id:
                    continue
                self.assertEqual(parent.island_id, node.island_id)

        best = result.state.nodes[result.final_recommendation.best_bet_node_id]
        conservative = result.state.nodes[result.final_recommendation.conservative_node_id]
        high_upside = result.state.nodes[result.final_recommendation.high_upside_node_id]
        self.assertEqual(best.island_id, "balanced")
        self.assertEqual(conservative.island_id, "conservative")
        self.assertEqual(high_upside.island_id, "upside")
        self.assertIn("## Search Islands", result.summary_markdown)
        self.assertIn("Balanced (`balanced`)", result.summary_markdown)
        self.assertIn("Conservative (`conservative`)", result.summary_markdown)
        self.assertIn("High Upside (`upside`)", result.summary_markdown)

        generate_calls = [
            call for call in provider.calls if call["action_name"] == "generate_seed"
        ]
        self.assertEqual(len(generate_calls), 3)
        self.assertEqual(
            {call["input_payload"]["island"]["island_id"] for call in generate_calls},
            {"balanced", "conservative", "upside"},
        )

    def test_runtime_migrates_candidates_between_islands_without_cross_island_parents(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations",
                seed_candidates_by_island={
                    "balanced": [_workflow_archive_candidate()],
                    "conservative": [_operational_assistant_candidate()],
                    "upside": [_benchmark_market_candidate()],
                },
            )
            runtime = SearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    seed_target=3,
                    stress_test_limit=1,
                    deepen_limit=1,
                    mutate_limit=1,
                    combine_limit=1,
                    migration_cooldown=3,
                    frontier_limit=3,
                    rejected_limit=2,
                    max_learning_notes=2,
                    compression_interval=6,
                    island_policies=(
                        balanced_island_policy(),
                        conservative_island_policy(),
                        upside_island_policy(),
                    ),
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=10,
                run_id="run-search-island-migration",
            )

        migration_calls = [call for call in provider.calls if call["action_name"] == "migrate"]
        migrated_nodes = [
            node
            for node in result.state.nodes.values()
            if node.action_type is ActionType.MIGRATE and node.node_id in result.state.archive_ids
        ]

        self.assertEqual(len(migration_calls), 1)
        self.assertEqual(len(migrated_nodes), 1)
        migrated = migrated_nodes[0]
        self.assertEqual(migrated.island_id, "upside")
        self.assertEqual(migrated.parent_ids, [result.state.root_id])
        self.assertEqual(migrated.metadata["migration"]["source_island_id"], "balanced")
        self.assertEqual(migrated.metadata["migration"]["destination_island_id"], "upside")
        self.assertEqual(
            migration_calls[0]["input_payload"]["source_island"]["island_id"],
            "balanced",
        )
        self.assertEqual(
            migration_calls[0]["input_payload"]["destination_island"]["island_id"],
            "upside",
        )
        self.assertIn("## Island Migration", result.summary_markdown)

    def test_runtime_routes_actions_through_provider_pool_using_persisted_stats(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            store.merge_provider_routing_stats(
                ProviderRoutingStats(
                    entries=[
                        ProviderRoutingStatsEntry(
                            provider_name="gemini",
                            action_name="generate_seed",
                            run_count=2,
                            invocation_count=4,
                            provider_failure_count=0,
                            candidate_count=8,
                            scored_node_count=8,
                            admitted_count=6,
                            rejected_count=1,
                            hard_fail_count=1,
                            strong_score_count=4,
                            stress_test_survivor_count=3,
                            winner_count=1,
                            winner_contribution_count=2,
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=25.2,
                            total_reward=10.5,
                            last_run_id="run-routing-gemini",
                            last_updated_at=datetime(2026, 3, 6, 15, 30, 0, tzinfo=timezone.utc),
                        ),
                        ProviderRoutingStatsEntry(
                            provider_name="opencode",
                            action_name="evaluate_candidate",
                            run_count=2,
                            invocation_count=4,
                            provider_failure_count=0,
                            candidate_count=8,
                            scored_node_count=8,
                            admitted_count=6,
                            rejected_count=1,
                            hard_fail_count=1,
                            strong_score_count=4,
                            stress_test_survivor_count=3,
                            winner_count=1,
                            winner_contribution_count=2,
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=25.2,
                            total_reward=10.5,
                            last_run_id="run-routing-opencode-eval",
                            last_updated_at=datetime(2026, 3, 6, 15, 30, 30, tzinfo=timezone.utc),
                        ),
                        ProviderRoutingStatsEntry(
                            provider_name="gemini",
                            action_name="assess_novelty",
                            run_count=2,
                            invocation_count=4,
                            provider_failure_count=0,
                            candidate_count=8,
                            scored_node_count=8,
                            admitted_count=6,
                            rejected_count=1,
                            hard_fail_count=1,
                            strong_score_count=4,
                            stress_test_survivor_count=3,
                            winner_count=1,
                            winner_contribution_count=2,
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=25.2,
                            total_reward=10.5,
                            last_run_id="run-routing-gemini-novelty",
                            last_updated_at=datetime(2026, 3, 6, 15, 30, 45, tzinfo=timezone.utc),
                        ),
                        ProviderRoutingStatsEntry(
                            provider_name="opencode",
                            action_name="rank",
                            run_count=2,
                            invocation_count=3,
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
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=0.0,
                            total_reward=3.0,
                            last_run_id="run-routing-opencode",
                            last_updated_at=datetime(2026, 3, 6, 15, 31, 0, tzinfo=timezone.utc),
                        ),
                    ],
                    updated_at=datetime(2026, 3, 6, 15, 31, 0, tzinfo=timezone.utc),
                )
            )
            codex_provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations" / "codex",
                name="codex",
            )
            gemini_provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations" / "gemini",
                name="gemini",
            )
            opencode_provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations" / "opencode",
                name="opencode",
            )
            runtime = SearchRuntime(
                provider=codex_provider,
                providers=[codex_provider, gemini_provider, opencode_provider],
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
                run_id="run-search-routed-provider-pool",
            )
            self.assertTrue(
                any(call["action_name"] == "generate_seed" for call in gemini_provider.calls)
            )
            self.assertFalse(
                any(call["action_name"] == "generate_seed" for call in codex_provider.calls)
            )
            self.assertTrue(
                any(
                    call["action_name"] in {"assess_novelty", "assess_novelty_batch"}
                    for call in gemini_provider.calls
                )
            )
            self.assertFalse(
                any(
                    call["action_name"] in {"assess_novelty", "assess_novelty_batch"}
                    for call in codex_provider.calls
                )
            )
            self.assertTrue(
                any(
                    call["action_name"] in {
                        "evaluate_candidate",
                        "evaluate_candidate_batch",
                    }
                    for call in opencode_provider.calls
                )
            )
            self.assertTrue(
                any(call["action_name"] == "rank" for call in opencode_provider.calls)
            )
            self.assertTrue(
                all(
                    node.provider_name == "gemini"
                    for node in result.state.nodes.values()
                    if node.action_type is ActionType.GENERATE_SEED
                )
            )
            root_routing = result.state.nodes[result.state.root_id].metadata["provider_routing"]
            self.assertEqual(root_routing["evaluate_candidate"], ["opencode"])
            for node in result.state.nodes.values():
                if node.node_id == result.state.root_id:
                    continue
                provider_routing = node.metadata["provider_routing"]
                self.assertEqual(provider_routing["assess_novelty"], ["gemini"])
                self.assertEqual(provider_routing["evaluate_candidate"], ["opencode"])
            eval_entry = next(
                entry
                for entry in store.load_provider_routing_stats().entries
                if entry.provider_name == "opencode"
                and entry.action_name == "evaluate_candidate"
            )
            self.assertGreaterEqual(eval_entry.invocation_count, len(result.state.nodes))
            rank_entry = next(
                entry
                for entry in store.load_provider_routing_stats().entries
                if entry.provider_name == "opencode" and entry.action_name == "rank"
            )
            self.assertGreaterEqual(rank_entry.invocation_count, 1)
            novelty_entry = next(
                entry
                for entry in store.load_provider_routing_stats().entries
                if entry.provider_name == "gemini"
                and entry.action_name == "assess_novelty"
            )
            self.assertGreaterEqual(
                novelty_entry.invocation_count,
                len(result.state.nodes) - 1,
            )

    def test_runtime_falls_back_to_other_providers_when_routed_provider_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            store.merge_provider_routing_stats(
                ProviderRoutingStats(
                    entries=[
                        ProviderRoutingStatsEntry(
                            provider_name="gemini",
                            action_name="generate_seed",
                            run_count=2,
                            invocation_count=4,
                            provider_failure_count=0,
                            candidate_count=8,
                            scored_node_count=8,
                            admitted_count=6,
                            rejected_count=1,
                            hard_fail_count=1,
                            strong_score_count=4,
                            stress_test_survivor_count=3,
                            winner_count=1,
                            winner_contribution_count=2,
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=25.2,
                            total_reward=10.5,
                            last_run_id="run-routing-gemini-generate",
                            last_updated_at=datetime(2026, 3, 6, 15, 30, 0, tzinfo=timezone.utc),
                        ),
                        ProviderRoutingStatsEntry(
                            provider_name="gemini",
                            action_name="assess_novelty",
                            run_count=2,
                            invocation_count=4,
                            provider_failure_count=0,
                            candidate_count=8,
                            scored_node_count=8,
                            admitted_count=6,
                            rejected_count=1,
                            hard_fail_count=1,
                            strong_score_count=4,
                            stress_test_survivor_count=3,
                            winner_count=1,
                            winner_contribution_count=2,
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=25.2,
                            total_reward=10.5,
                            last_run_id="run-routing-gemini-novelty",
                            last_updated_at=datetime(2026, 3, 6, 15, 30, 15, tzinfo=timezone.utc),
                        ),
                        ProviderRoutingStatsEntry(
                            provider_name="opencode",
                            action_name="evaluate_candidate",
                            run_count=2,
                            invocation_count=4,
                            provider_failure_count=0,
                            candidate_count=8,
                            scored_node_count=8,
                            admitted_count=6,
                            rejected_count=1,
                            hard_fail_count=1,
                            strong_score_count=4,
                            stress_test_survivor_count=3,
                            winner_count=1,
                            winner_contribution_count=2,
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=25.2,
                            total_reward=10.5,
                            last_run_id="run-routing-opencode-eval",
                            last_updated_at=datetime(2026, 3, 6, 15, 30, 30, tzinfo=timezone.utc),
                        ),
                        ProviderRoutingStatsEntry(
                            provider_name="opencode",
                            action_name="rank",
                            run_count=2,
                            invocation_count=3,
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
                            critique_count=0,
                            useful_critique_count=0,
                            learning_note_count=0,
                            accumulated_score=0.0,
                            total_reward=3.0,
                            last_run_id="run-routing-opencode-rank",
                            last_updated_at=datetime(2026, 3, 6, 15, 31, 0, tzinfo=timezone.utc),
                        ),
                    ],
                    updated_at=datetime(2026, 3, 6, 15, 31, 0, tzinfo=timezone.utc),
                )
            )
            codex_provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations" / "codex",
                name="codex",
            )
            gemini_provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations" / "gemini",
                name="gemini",
                fail_actions={"generate_seed", "assess_novelty", "assess_novelty_batch"},
            )
            opencode_provider = SearchFixtureProvider(
                root / "artifacts" / "provider_invocations" / "opencode",
                name="opencode",
                fail_actions={"evaluate_candidate", "evaluate_candidate_batch", "rank"},
            )
            runtime = SearchRuntime(
                provider=codex_provider,
                providers=[codex_provider, gemini_provider, opencode_provider],
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
                run_id="run-search-provider-fallback",
            )
            loaded = store.load_run("run-search-provider-fallback")

        self.assertEqual(result.manifest.status, RunStatus.COMPLETED)
        self.assertEqual(loaded.manifest.status, RunStatus.COMPLETED)
        self.assertTrue(any(call["action_name"] == "generate_seed" for call in gemini_provider.calls))
        self.assertTrue(
            any(
                call["action_name"] in {"assess_novelty", "assess_novelty_batch"}
                for call in gemini_provider.calls
            )
        )
        self.assertTrue(
            any(
                call["action_name"] in {
                    "evaluate_candidate",
                    "evaluate_candidate_batch",
                }
                for call in opencode_provider.calls
            )
        )
        self.assertTrue(any(call["action_name"] == "rank" for call in opencode_provider.calls))
        self.assertTrue(any(call["action_name"] == "generate_seed" for call in codex_provider.calls))
        self.assertTrue(
            any(
                call["action_name"] in {"assess_novelty", "assess_novelty_batch"}
                for call in codex_provider.calls
            )
        )
        self.assertTrue(
            any(
                call["action_name"] in {
                    "evaluate_candidate",
                    "evaluate_candidate_batch",
                }
                for call in codex_provider.calls
            )
        )
        self.assertTrue(any(call["action_name"] == "rank" for call in codex_provider.calls))
        self.assertTrue(
            all(
                node.provider_name == "codex"
                for node in result.state.nodes.values()
                if node.action_type is ActionType.GENERATE_SEED
            )
        )
        root_routing = result.state.nodes[result.state.root_id].metadata["provider_routing"]
        self.assertEqual(root_routing["evaluate_candidate"], ["codex"])
        for node in result.state.nodes.values():
            if node.node_id == result.state.root_id:
                continue
            provider_routing = node.metadata["provider_routing"]
            self.assertEqual(provider_routing["assess_novelty"], ["codex"])
            self.assertEqual(provider_routing["evaluate_candidate"], ["codex"])
        routing_entries = {
            (entry.provider_name, entry.action_name): entry
            for entry in loaded.routing_summary.entries
        }
        self.assertGreaterEqual(
            routing_entries[("gemini", "generate_seed")].provider_failure_count,
            1,
        )
        self.assertGreaterEqual(
            routing_entries[("gemini", "assess_novelty")].provider_failure_count,
            1,
        )
        self.assertGreaterEqual(
            routing_entries[("opencode", "evaluate_candidate")].provider_failure_count,
            1,
        )
        self.assertGreaterEqual(
            routing_entries[("opencode", "rank")].provider_failure_count,
            1,
        )
        self.assertGreaterEqual(
            routing_entries[("codex", "generate_seed")].candidate_count,
            1,
        )
        self.assertGreaterEqual(
            routing_entries[("codex", "evaluate_candidate")].candidate_count,
            len(result.state.nodes),
        )

    def test_pairwise_tournament_can_rescue_a_third_ranked_finalist(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = FileSystemStateStore(root / "artifacts" / "runs")
            provider = TournamentFixtureProvider(root / "artifacts" / "provider_invocations")
            runtime = SearchRuntime(
                provider=provider,
                state_store=store,
                policy=SearchPolicy(
                    seed_target=3,
                    stress_test_limit=1,
                    deepen_limit=1,
                    mutate_limit=1,
                    combine_limit=1,
                    frontier_limit=3,
                    rejected_limit=1,
                    max_learning_notes=1,
                ),
            )

            result = runtime.run(
                request="Design the best retention strategy for a workflow-heavy product.",
                budget=2,
                run_id="run-search-pairwise-tournament",
            )
            loaded = store.load_run("run-search-pairwise-tournament")

        rank_calls = [call for call in provider.calls if call["action_name"] == "rank"]

        self.assertEqual(result.final_recommendation.best_bet_node_id, "node-0004")
        self.assertEqual(result.final_recommendation.conservative_node_id, "node-0003")
        self.assertEqual(result.final_recommendation.high_upside_node_id, "node-0002")
        self.assertEqual(len(result.final_recommendation.pairwise_decisions), 4)
        self.assertEqual(
            result.final_recommendation.pairwise_decisions[0].objective_name,
            "best_overall",
        )
        self.assertEqual(loaded.final_recommendation, result.final_recommendation)
        self.assertEqual(len(rank_calls), 4)
        self.assertIn("Best bet: `node-0004` beat `node-0002`.", result.summary_markdown)


def _max_overlap(
    calls: list[dict[str, object]],
    *,
    actions: set[str] | None = None,
) -> int:
    events: list[tuple[float, int]] = []
    for call in calls:
        action_name = str(call["action_name"])
        if actions is not None and action_name not in actions:
            continue
        events.append((float(call["started_at"]), 1))
        events.append((float(call["finished_at"]), -1))

    active = 0
    max_active = 0
    for _, delta in sorted(events, key=lambda item: (item[0], -item[1])):
        active += delta
        max_active = max(max_active, active)
    return max_active


class TournamentFixtureProvider(SearchFixtureProvider):
    def _handle_generate_seed(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        target_count = int(input_payload["target_count"])
        templates = [
            _tournament_candidate_payload(
                thesis="Activation checklist wedge",
                mechanism=(
                    "Start with an easy-to-ship checklist layer that nudges teams into the product."
                ),
            ),
            _tournament_candidate_payload(
                thesis="Operational ritual scaffold",
                mechanism=(
                    "Build around a clearly defined recurring team ritual with explicit rollout steps."
                ),
            ),
            _tournament_candidate_payload(
                thesis="Workflow-native archive with compounding reviews",
                mechanism=(
                    "Anchor the product in a recurring review loop that compounds prior team decisions into future speed."
                ),
            ),
        ]
        candidates = [templates[index % len(templates)] for index in range(target_count)]
        return {
            "candidates": candidates,
            "batch_summary": "Generated three viable finalists with different score and pairwise profiles.",
        }

    def _handle_assess_novelty(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "novelty_score": 0.82,
            "max_similarity": 0.24,
            "nearest_neighbor_id": None,
            "similarity_threshold": input_payload["similarity_threshold"],
            "is_novel": True,
            "summary": "The candidate is distinct enough to enter the tournament.",
            "duplicate_signals": [],
        }

    def _handle_evaluate_candidate(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        thesis = str(input_payload["candidate"]["thesis"])
        if thesis == "Activation checklist wedge":
            return _tournament_evaluation_payload(
                total_score=6.9,
                implementation_tractability=0.92,
                upside=0.62,
                distinctiveness=0.58,
                usefulness=0.77,
                specificity=0.76,
                plausibility=0.88,
                adversarial_robustness=0.72,
                evidence_quality=0.68,
                confidence_estimate=0.85,
                summary="Fast to ship and tractable, but strategically narrow.",
            )
        if thesis == "Operational ritual scaffold":
            return _tournament_evaluation_payload(
                total_score=6.6,
                implementation_tractability=0.86,
                upside=0.71,
                distinctiveness=0.66,
                usefulness=0.83,
                specificity=0.84,
                plausibility=0.84,
                adversarial_robustness=0.8,
                evidence_quality=0.73,
                confidence_estimate=0.83,
                summary="The safest serious option with a clear rollout shape.",
            )
        return _tournament_evaluation_payload(
            total_score=6.2,
            implementation_tractability=0.74,
            upside=0.9,
            distinctiveness=0.88,
            usefulness=0.9,
            specificity=0.89,
            plausibility=0.79,
            adversarial_robustness=0.78,
            evidence_quality=0.76,
            confidence_estimate=0.78,
            summary="Third by score, but strongest once pairwise tradeoffs are examined directly.",
        )

    def _handle_rank(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        objective_name = str(input_payload["objective"]["name"])
        left_candidate = str(input_payload["left"]["candidate"]["thesis"])
        right_candidate = str(input_payload["right"]["candidate"]["thesis"])

        if objective_name == "best_overall":
            preferred = "Workflow-native archive with compounding reviews"
            if left_candidate == preferred:
                return _tournament_pairwise_payload(
                    winner="left",
                    summary="The workflow-native archive wins because it compounds value over time instead of only improving activation mechanics.",
                )
            if right_candidate == preferred:
                return _tournament_pairwise_payload(
                    winner="right",
                    summary="The workflow-native archive wins because it compounds value over time instead of only improving activation mechanics.",
                )

        if objective_name == "conservative_option":
            preferred = "Operational ritual scaffold"
            if left_candidate == preferred:
                return _tournament_pairwise_payload(
                    winner="left",
                    summary="The operational ritual scaffold is the safer serious option because it keeps the rollout controlled without collapsing into a shallow wedge.",
                )
            if right_candidate == preferred:
                return _tournament_pairwise_payload(
                    winner="right",
                    summary="The operational ritual scaffold is the safer serious option because it keeps the rollout controlled without collapsing into a shallow wedge.",
                )

        if objective_name == "high_upside_option":
            preferred = "Activation checklist wedge"
            if left_candidate == preferred:
                return _tournament_pairwise_payload(
                    winner="left",
                    summary="The activation checklist wedge remains the remaining high-upside option because it can move quickly even if its moat is thinner.",
                )
            if right_candidate == preferred:
                return _tournament_pairwise_payload(
                    winner="right",
                    summary="The activation checklist wedge remains the remaining high-upside option because it can move quickly even if its moat is thinner.",
                )

        return _tournament_pairwise_payload(
            winner="left",
            summary="The left candidate wins the fallback score-backed comparison.",
        )


def _tournament_candidate_payload(*, thesis: str, mechanism: str) -> dict[str, object]:
    return {
        "thesis": thesis,
        "mechanism": mechanism,
        "assumptions": ["Teams care about faster recurring work."],
        "strengths": ["Solves a real operator problem."],
        "failure_modes": ["Could still miss long-term retention."],
        "unknowns": ["Which workflow will adopt first?"],
        "implementation_shape": "A focused initial rollout.",
        "evidence": ["The product brief prioritizes durable workflow retention."],
    }


def _tournament_evaluation_payload(
    *,
    total_score: float,
    implementation_tractability: float,
    upside: float,
    distinctiveness: float,
    usefulness: float,
    specificity: float,
    plausibility: float,
    adversarial_robustness: float,
    evidence_quality: float,
    confidence_estimate: float,
    summary: str,
) -> dict[str, object]:
    return {
        "score": {
            "hard_constraint_pass": True,
            "hard_constraint_reasons": [],
            "distinctiveness": distinctiveness,
            "usefulness": usefulness,
            "specificity": specificity,
            "plausibility": plausibility,
            "implementation_tractability": implementation_tractability,
            "upside": upside,
            "adversarial_robustness": adversarial_robustness,
            "evidence_quality": evidence_quality,
            "total_score": total_score,
            "confidence_estimate": confidence_estimate,
        },
        "summary": summary,
        "strengths": ["Clear mechanism."],
        "weaknesses": ["The tradeoffs are still real."],
        "open_questions": ["How well will this hold up under live usage?"],
    }


def _tournament_pairwise_payload(*, winner: str, summary: str) -> dict[str, object]:
    return {
        "winner": winner,
        "summary": summary,
        "decisive_advantages": ["The mechanism better matches the objective."],
        "decisive_risks": ["Execution still matters."],
        "confidence": 0.8,
    }
