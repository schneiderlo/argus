from __future__ import annotations

from datetime import datetime, timezone
import unittest

from argus.errors import ArgusValidationError
from argus.models import (
    AdversarialReview,
    Candidate,
    ComparisonMatrix,
    ComparisonMatrixRow,
    CoverageLedger,
    CoverageStatus,
    DeepDiveDoc,
    FinalDecisionDoc,
    HybridAssessment,
    HybridVerdict,
    ProposalBrief,
    ProposalDisposition,
    ProposalTriageDecision,
    ResearchSchedulerAction,
    ResearchArtifactBundle,
    SchedulerDecision,
    SearchAxis,
    SearchCell,
    SearchSpaceFrame,
    TriageReport,
)


class ResearchModelTests(unittest.TestCase):
    def test_research_artifact_bundle_round_trips_full_decision_bundle(self) -> None:
        frame = SearchSpaceFrame(
            frame_id="frame-001",
            problem_statement="Choose the best operator-facing research workflow for Argus.",
            target_decision="Pick the default research runtime to ship next.",
            hard_gates=["Must remain auditable.", "Must fit local filesystem persistence."],
            soft_criteria=["Decision quality", "Latency", "Operator trust"],
            baseline_options=["Keep the adaptive node runtime as default."],
            axes=[
                SearchAxis(
                    axis_id="coverage",
                    label="Coverage strategy",
                    description="How explicitly the runtime plans search-space coverage.",
                    options=["implicit frontier", "explicit ledger"],
                    rationale="Coverage visibility determines scheduler quality.",
                ),
                SearchAxis(
                    axis_id="authoring",
                    label="Authoring depth",
                    description="How much structured artifact authoring each survivor receives.",
                    options=["candidate summary", "decision dossier"],
                ),
            ],
            coverage_plan=[
                "Seed at least one representative for each high-value cell.",
                "Red-team any family that still carries material hard-gate risk.",
            ],
            notes=["Keep compact runtime available as a benchmark control."],
        )
        ledger = CoverageLedger(
            ledger_id="ledger-001",
            frame_id=frame.frame_id,
            cells=[
                SearchCell(
                    cell_id="cell-implicit-light",
                    label="Implicit + light authoring",
                    axis_assignments={
                        "coverage": "implicit frontier",
                        "authoring": "candidate summary",
                    },
                    hypothesis="Fastest path, but likely too lossy for decision-grade output.",
                    coverage_status=CoverageStatus.TRIAGED,
                    uncertainty=0.35,
                    hard_gate_risk=0.65,
                    evidence_strength=0.55,
                    incumbent_proposal_ids=["proposal-a"],
                    notes=["Current runtime mostly lives here."],
                ),
                SearchCell(
                    cell_id="cell-explicit-deep",
                    label="Explicit + deep authoring",
                    axis_assignments={
                        "coverage": "explicit ledger",
                        "authoring": "decision dossier",
                    },
                    hypothesis="Higher authoring cost, but materially stronger final decisions.",
                    coverage_status=CoverageStatus.REDTEAMED,
                    uncertainty=0.25,
                    hard_gate_risk=0.2,
                    evidence_strength=0.8,
                    incumbent_proposal_ids=["proposal-b"],
                ),
            ],
            coverage_summary="The explicit-ledger path is the current leader after red-teaming.",
            next_questions=["Can we keep its latency within the standard cost profile?"],
            updated_at=datetime(2026, 3, 8, 18, 30, 0, tzinfo=timezone.utc),
        )
        proposal_a = ProposalBrief(
            proposal_id="proposal-a",
            cell_id="cell-implicit-light",
            title="Adaptive runtime with richer finish stage",
            summary="Retain current scheduler and add a decision-authoring stage at the end.",
            candidate=_sample_candidate(
                thesis="Keep the adaptive runtime and add a typed decision-authoring finisher.",
            ),
            seed_rationale="Low migration cost and immediate leverage on the existing archive.",
            open_questions=["Will the finish stage have enough evidence without a coverage ledger?"],
            evidence=["Current runtime already ranks and red-teams candidates."],
            parent_node_ids=["node-0007"],
        )
        proposal_b = ProposalBrief(
            proposal_id="proposal-b",
            cell_id="cell-explicit-deep",
            title="Coverage-led research runtime",
            summary="Make search-space framing and family-level coverage the default control loop.",
            candidate=_sample_candidate(
                thesis="Adopt a coverage-led runtime with first-class research artifacts.",
            ),
            seed_rationale="Matches the paper-aligned product direction and auditability goals.",
            open_questions=["How much concurrent authoring can we add without destabilizing persistence?"],
            evidence=["Specs require explicit coverage state and decision-grade outputs."],
            parent_node_ids=["node-0011"],
        )
        triage = TriageReport(
            report_id="triage-001",
            frame_id=frame.frame_id,
            decisions=[
                ProposalTriageDecision(
                    proposal_id=proposal_a.proposal_id,
                    disposition=ProposalDisposition.ELIMINATE,
                    rationale="Improves output shape, but still under-plans coverage.",
                    follow_up="Keep it as the control benchmark mode.",
                ),
                ProposalTriageDecision(
                    proposal_id=proposal_b.proposal_id,
                    disposition=ProposalDisposition.SURVIVE,
                    rationale="Best match for the required coverage-led architecture.",
                    follow_up="Deepen the persistence and scheduler design.",
                ),
            ],
            survivor_ids=[proposal_b.proposal_id],
            unexplored_cell_ids=[],
            summary="The explicit-ledger family survives because it closes the main product gap.",
            next_actions=["Write the deep-dive dossier for the surviving family."],
        )
        deep_dive = DeepDiveDoc(
            doc_id="deep-001",
            proposal_id=proposal_b.proposal_id,
            title="Coverage-led runtime design",
            executive_summary="Separate scheduling from authoring and persist every decision artifact.",
            detailed_mechanism="Frame the search space, maintain a ledger, deepen incumbents, red-team them, then write a final decision doc.",
            implementation_plan=[
                "Add typed artifact bundle persistence to the run store.",
                "Add provider actions for framing, seeding, triage, deepening, and red-teaming.",
            ],
            key_unknowns=["Whether family-level triage is enough without cell-level hybrids."],
            supporting_evidence=["The specs require explicit coverage planning and typed artifacts."],
            assumptions=["Provider-backed judging remains the main evaluator path."],
        )
        review = AdversarialReview(
            review_id="review-001",
            proposal_id=proposal_b.proposal_id,
            thesis_under_test=proposal_b.candidate.thesis,
            hidden_dependencies=["The store must support a bundle without making replay fragile."],
            failure_modes=["The authoring layer could add too much serial latency."],
            mitigations=["Keep provider dispatch concurrent and state commits deterministic."],
            summary="The approach is viable if persistence and concurrency stay bounded.",
            verdict="Proceed, but keep latency budget explicit.",
            confidence=0.72,
            evidence=["Existing concurrent provider dispatch already preserves deterministic admission."],
        )
        matrix = ComparisonMatrix(
            matrix_id="matrix-001",
            frame_id=frame.frame_id,
            criteria=["decision_quality", "latency", "operator_auditability"],
            rows=[
                ComparisonMatrixRow(
                    proposal_id=proposal_a.proposal_id,
                    criterion_scores={
                        "decision_quality": 0.58,
                        "latency": 0.82,
                        "operator_auditability": 0.49,
                    },
                    advantages=["Lower implementation cost."],
                    liabilities=["Still compresses too much decision work."],
                    takeaway="Useful control, weak default.",
                ),
                ComparisonMatrixRow(
                    proposal_id=proposal_b.proposal_id,
                    criterion_scores={
                        "decision_quality": 0.88,
                        "latency": 0.54,
                        "operator_auditability": 0.9,
                    },
                    advantages=["Strongest audit trail and decision quality."],
                    liabilities=["Higher authoring and persistence complexity."],
                    takeaway="Best default if latency stays bounded.",
                ),
            ],
            summary="The coverage-led runtime wins on the criteria that matter most to Argus.",
        )
        hybrid = HybridAssessment(
            assessment_id="hybrid-001",
            source_proposal_ids=[proposal_a.proposal_id, proposal_b.proposal_id],
            hybrid_name="Coverage-led scheduler with lean control fallback",
            seam_hypothesis="Use the adaptive runtime as a bounded fallback inside uncovered low-value cells.",
            repaired_failure_mode="Reduce the coverage-led path's worst-case latency on dominated regions.",
            complementary_strengths=[
                "Coverage-led planning improves search quality.",
                "Adaptive fallback reduces unnecessary authoring overhead.",
            ],
            complexity_tax="Introduces dual-mode scheduling and more artifact routing logic.",
            expected_upside="Could preserve decision quality while reducing tail latency.",
            open_questions=["Whether the seam stays explainable to operators."],
            verdict=HybridVerdict.HOLD,
            summary="Promising, but not yet justified over shipping the pure coverage-led path first.",
        )
        decision = FinalDecisionDoc(
            decision_id="decision-001",
            frame_id=frame.frame_id,
            selected_proposal_id=proposal_b.proposal_id,
            runner_up_proposal_id=proposal_a.proposal_id,
            conservative_proposal_id=proposal_a.proposal_id,
            high_upside_proposal_id=proposal_b.proposal_id,
            summary="Ship the coverage-led runtime and keep the adaptive path as the benchmark control.",
            decision_rule="Prefer the option that most improves decision quality without violating deterministic persistence.",
            assumptions=["Artifact persistence will stay inspectable with normal shell tools."],
            top_risks=["Authoring latency could erase operator trust."],
            mitigations=["Batch independent provider work and commit results in stable order."],
            first_spike=["Persist a typed research-artifact bundle under each run."],
            kill_criteria=["If bundle persistence makes replay or verification brittle."],
            next_experiments=["Benchmark the research runtime against adaptive and staged baselines."],
            reversal_conditions=["If benchmarks show no material decision-quality gain."],
            rejected_proposal_ids=[],
        )
        scheduler_decision = SchedulerDecision(
            decision_id="schedule-001",
            action=ResearchSchedulerAction.REDTEAM,
            rationale="Attack the leading family because its latency risk is still material.",
            remaining_budget=2,
            priority_score=0.64,
            target_proposal_ids=[proposal_b.proposal_id],
            signals=["proposal-b via cell-explicit-deep: uncertainty=0.25 hard_gate_risk=0.20 evidence_strength=0.80"],
            selected_at=datetime(2026, 3, 8, 18, 45, 0, tzinfo=timezone.utc),
        )

        bundle = ResearchArtifactBundle(
            search_space_frame=frame,
            coverage_ledger=ledger,
            scheduler_decisions=[scheduler_decision],
            proposal_briefs=[proposal_a, proposal_b],
            triage_reports=[triage],
            deep_dive_docs=[deep_dive],
            adversarial_reviews=[review],
            comparison_matrices=[matrix],
            hybrid_assessments=[hybrid],
            final_decision_doc=decision,
        )

        payload = bundle.to_dict()
        restored = ResearchArtifactBundle.from_dict(payload)

        self.assertEqual(bundle, restored)
        self.assertEqual(payload["search_space_frame"]["axes"][0]["axis_id"], "coverage")
        self.assertEqual(payload["coverage_ledger"]["cells"][1]["coverage_status"], "redteamed")
        self.assertEqual(payload["scheduler_decisions"][0]["action"], "redteam")
        self.assertEqual(payload["final_decision_doc"]["selected_proposal_id"], "proposal-b")

    def test_bundle_rejects_cells_that_do_not_match_frame_axis_options(self) -> None:
        frame = SearchSpaceFrame(
            frame_id="frame-002",
            problem_statement="Choose the next runtime mode.",
            target_decision="Select one runtime.",
            hard_gates=["Stay deterministic."],
            soft_criteria=["Quality"],
            baseline_options=["Adaptive runtime"],
            axes=[
                SearchAxis(
                    axis_id="coverage",
                    label="Coverage",
                    description="Coverage planning mode.",
                    options=["implicit frontier", "explicit ledger"],
                )
            ],
            coverage_plan=["Compare both coverage modes."],
        )
        ledger = CoverageLedger(
            ledger_id="ledger-002",
            frame_id=frame.frame_id,
            cells=[
                SearchCell(
                    cell_id="cell-invalid",
                    label="Broken cell",
                    axis_assignments={"coverage": "random choice"},
                    hypothesis="Invalid option should fail.",
                )
            ],
            coverage_summary="Invalid.",
        )

        with self.assertRaises(ArgusValidationError):
            ResearchArtifactBundle(search_space_frame=frame, coverage_ledger=ledger)

    def test_triage_report_requires_survivor_ids_to_match_survive_decisions(self) -> None:
        with self.assertRaises(ArgusValidationError):
            TriageReport(
                report_id="triage-002",
                frame_id="frame-003",
                decisions=[
                    ProposalTriageDecision(
                        proposal_id="proposal-a",
                        disposition=ProposalDisposition.SURVIVE,
                        rationale="Keep it.",
                    )
                ],
                survivor_ids=[],
                unexplored_cell_ids=[],
                summary="Inconsistent report.",
            )


def _sample_candidate(*, thesis: str) -> Candidate:
    return Candidate(
        thesis=thesis,
        mechanism="Use typed artifacts and provider-backed evaluation to keep decisions auditable.",
        assumptions=["Operators prefer reproducible search over one-shot ideation."],
        strengths=["Improves auditability."],
        failure_modes=["Can add authoring overhead."],
        unknowns=["Exact latency impact of richer artifacts."],
        evidence=["The specs require durable decision-grade artifacts."],
    )
