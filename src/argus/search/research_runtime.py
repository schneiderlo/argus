from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from argus.errors import ArgusValidationError
from argus.models import (
    ActionType,
    Candidate,
    FinalRecommendation,
    JSONValue,
    LearningNote,
    LearningNoteType,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ProposalBrief,
    ResearchSchedulerAction,
    ResearchArtifactBundle,
    SchedulerDecision,
    SearchState,
    TriageReport,
)
from argus.models.research import CoverageLedger, CoverageStatus, SearchCell, SearchSpaceFrame
from argus.search.research_contracts import (
    FinalDecisionPackage,
    ProposalSeedBatch,
    SearchSpacePlan,
    adversarial_review_schema,
    deep_dive_doc_schema,
    final_decision_package_schema,
    hybrid_assessment_schema,
    proposal_seed_batch_schema,
    search_space_plan_schema,
    triage_report_schema,
)
from argus.search.runtime import (
    SearchRuntime,
    _MutableSession,
    _ProviderActionRequest,
    _RoutingTracker,
    _evaluation_metadata,
    _provider_routing_metadata,
    _utcnow,
    balanced_island_policy,
)
from argus.storage import RunStatus


@dataclass(frozen=True, slots=True)
class ResearchRunResult:
    run_path: Path
    manifest: object
    state: SearchState
    research_bundle: ResearchArtifactBundle
    final_recommendation: FinalRecommendation
    summary_markdown: str


@dataclass(frozen=True, slots=True)
class _ResearchProposalRecord:
    brief: ProposalBrief
    node_id: str


class ResearchRuntime(SearchRuntime):
    """Coverage-led research runtime that persists a typed artifact bundle."""

    _MIN_RESEARCH_BUDGET = 4

    def run(
        self,
        *,
        request: str,
        budget: int,
        run_id: str | None = None,
    ) -> ResearchRunResult:
        normalized_request = request.strip()
        if not normalized_request:
            raise ArgusValidationError("request must not be empty.")
        return self.run_problem(
            problem_spec=ProblemSpec(
                request=normalized_request,
                constraints=[],
                success_criteria=[],
                context={},
            ),
            budget=budget,
            run_id=run_id,
        )

    def run_problem(
        self,
        *,
        problem_spec: ProblemSpec,
        budget: int,
        run_id: str | None = None,
    ) -> ResearchRunResult:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        if not isinstance(budget, int) or budget < self._MIN_RESEARCH_BUDGET:
            raise ArgusValidationError(
                f"research runtime requires budget >= {self._MIN_RESEARCH_BUDGET}."
            )

        initial_problem_spec = ProblemSpec(
            request=problem_spec.request,
            constraints=list(problem_spec.constraints),
            success_criteria=list(problem_spec.success_criteria),
            context={
                **problem_spec.context,
                "requested_provider": self.provider.name,
                "provider_pool": list(self.providers),
                "runtime_mode": "research",
            },
        )
        self._action_router = self._build_action_router()
        manifest = self._state_store.create_run(
            problem_spec=initial_problem_spec,
            provider_name=self.provider.name,
            budget=budget,
            run_id=run_id,
            metadata={
                "runtime": "research_v1",
                "runtime_mode": "research",
                "provider_pool": list(self.providers),
                "search_profile": "research",
                "island_ids": ["balanced"],
            },
        )
        self._active_run_id = manifest.run_id
        reusable_learning_context = self._select_reusable_learning_context(initial_problem_spec)
        if reusable_learning_context.entries:
            self._state_store.save_reusable_learning_context(
                manifest.run_id,
                reusable_learning_context,
            )
        self._emit_progress(
            "run_started",
            run_id=manifest.run_id,
            step_count=0,
            budget_spent=0,
            payload={
                "request": initial_problem_spec.request,
                "budget": budget,
                "provider_pool": list(self.providers),
                "provider": self.provider.name,
                "runtime_mode": "research",
            },
        )

        routing_tracker = _RoutingTracker(default_provider_name=self.provider.name)
        session: _MutableSession | None = None
        current_action = ActionType.FRAME_SEARCH_SPACE.value
        bundle = ResearchArtifactBundle()
        proposal_records: dict[str, _ResearchProposalRecord] = {}
        try:
            plan_response = self._run_provider_action(
                routing_tracker,
                action_name=ActionType.FRAME_SEARCH_SPACE,
                problem_spec=initial_problem_spec,
                input_payload=self._frame_search_space_payload(
                    problem_spec=initial_problem_spec,
                    budget=budget,
                    reusable_learning_notes=reusable_learning_context.entries,
                ),
                output_schema=search_space_plan_schema(),
            )
            plan = _validate_search_space_plan(plan_response.payload)
            current_action = "evaluate_candidate"
            root_candidate = _frame_candidate_from_search_space(plan.search_space_frame)
            root_assessment, evaluation_provider_name = self._evaluate_candidate(
                problem_spec=initial_problem_spec,
                candidate=root_candidate,
                novelty_score=1.0,
                reusable_learning_notes=reusable_learning_context.entries,
                routing_tracker=routing_tracker,
            )
            root_node = Node(
                node_id="node-0001",
                parent_ids=[],
                depth=0,
                action_type=ActionType.FRAME_SEARCH_SPACE,
                provider_name=plan_response.provider_name,
                candidate=root_candidate,
                island_id="balanced",
                score=root_assessment.score,
                novelty_score=1.0,
                lifecycle_status=NodeLifecycleStatus.ADMITTED,
                metadata={
                    "search_space_frame_id": plan.search_space_frame.frame_id,
                    "evaluation": _evaluation_metadata(root_assessment),
                    "provider_routing": _provider_routing_metadata(
                        evaluation_provider_names=(evaluation_provider_name,),
                    ),
                },
                created_at=_utcnow(),
            )
            session = _MutableSession(
                run_id=manifest.run_id,
                problem_spec=initial_problem_spec,
                root_node=root_node,
                budget_spent=1,
                step_count=1,
                island_policies=(balanced_island_policy(),),
            )
            session.set_reusable_learning_notes(reusable_learning_context.entries)
            session.refresh_frontier(limit=max(2, self.policy.frontier_limit))
            bundle = ResearchArtifactBundle(
                search_space_frame=plan.search_space_frame,
                coverage_ledger=plan.coverage_ledger,
            )
            self._emit_progress(
                "stage_completed",
                run_id=manifest.run_id,
                step_count=session.step_count,
                budget_spent=session.budget_spent,
                payload={
                    "action": ActionType.FRAME_SEARCH_SPACE.value,
                    "label": "Framing search space",
                    "nodes": len(session.nodes),
                    "archive": len(session.archive_ids),
                    "frontier": len(session.frontier_ids),
                },
            )
            self._persist_research_snapshot(
                manifest.run_id,
                session,
                bundle=bundle,
            )

            while budget - session.budget_spent > 1:
                scheduler_decision = self._select_scheduler_decision(
                    bundle=bundle,
                    proposal_records=proposal_records,
                    remaining_budget=budget - session.budget_spent,
                )
                bundle = replace(
                    bundle,
                    scheduler_decisions=[*bundle.scheduler_decisions, scheduler_decision],
                )
                self._emit_progress(
                    "research_scheduler_decision",
                    run_id=manifest.run_id,
                    step_count=session.step_count,
                    budget_spent=session.budget_spent,
                    payload={
                        "action": scheduler_decision.action.value,
                        "rationale": scheduler_decision.rationale,
                        "priority_score": scheduler_decision.priority_score,
                        "target_cell_ids": list(scheduler_decision.target_cell_ids),
                        "target_proposal_ids": list(scheduler_decision.target_proposal_ids),
                    },
                )
                self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)

                if scheduler_decision.action is ResearchSchedulerAction.STOP:
                    break

                if scheduler_decision.action is ResearchSchedulerAction.EXPAND:
                    current_action = ActionType.SEED_CELL_PROPOSALS.value
                    target_cells = self._cells_for_ids(
                        bundle.coverage_ledger,
                        scheduler_decision.target_cell_ids,
                    )
                    self._emit_progress(
                        "stage_started",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.SEED_CELL_PROPOSALS.value,
                            "label": "Seeding research cells",
                            "reason": scheduler_decision.rationale,
                            "target_cell_ids": list(scheduler_decision.target_cell_ids),
                        },
                    )
                    seed_response = self._run_provider_action(
                        routing_tracker,
                        action_name=ActionType.SEED_CELL_PROPOSALS,
                        problem_spec=session.problem_spec,
                        input_payload=self._seed_cell_payload(
                            frame=plan.search_space_frame,
                            ledger=bundle.coverage_ledger,
                            root_node=root_node,
                            reusable_learning_notes=session.reusable_learning_notes,
                            target_cells=target_cells,
                        ),
                        output_schema=proposal_seed_batch_schema(),
                    )
                    session.consume_budget()
                    seeded_batch = _validate_seed_batch(seed_response.payload)
                    admitted_nodes = self._admit_candidate_batch(
                        session,
                        island_id="balanced",
                        action_type=ActionType.SEED_CELL_PROPOSALS,
                        routing_tracker=routing_tracker,
                        requests=[
                            self._proposal_admission_request(
                                brief=brief,
                                root_id=session.root_id,
                                provider_name=seed_response.provider_name,
                            )
                            for brief in seeded_batch.proposals
                        ],
                    )
                    for brief, node in zip(seeded_batch.proposals, admitted_nodes):
                        proposal_records[brief.proposal_id] = _ResearchProposalRecord(
                            brief=brief,
                            node_id=node.node_id,
                        )
                    bundle = replace(
                        bundle,
                        proposal_briefs=[*bundle.proposal_briefs, *seeded_batch.proposals],
                        coverage_ledger=self._update_seeded_ledger(
                            ledger=bundle.coverage_ledger,
                            proposal_records=proposal_records,
                            state=session.snapshot(),
                        ),
                    )
                    session.refresh_frontier(limit=max(2, self.policy.frontier_limit))
                    self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)
                    self._emit_progress(
                        "stage_completed",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.SEED_CELL_PROPOSALS.value,
                            "label": "Seeding research cells",
                            "nodes": len(session.nodes),
                            "archive": len(session.archive_ids),
                            "frontier": len(session.frontier_ids),
                        },
                    )

                    current_action = ActionType.TRIAGE_PROPOSALS.value
                    self._emit_progress(
                        "stage_started",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.TRIAGE_PROPOSALS.value,
                            "label": "Triaging proposal families",
                            "reason": "Cull dominated families and mark any cells that still need expansion.",
                        },
                    )
                    triage_response = self._run_provider_action(
                        routing_tracker,
                        action_name=ActionType.TRIAGE_PROPOSALS,
                        problem_spec=session.problem_spec,
                        input_payload=self._triage_payload(
                            frame=plan.search_space_frame,
                            ledger=bundle.coverage_ledger,
                            proposal_records=proposal_records,
                            state=session.snapshot(),
                            reusable_learning_notes=session.reusable_learning_notes,
                        ),
                        output_schema=triage_report_schema(),
                    )
                    session.consume_budget()
                    triage_report = _validate_triage_report(triage_response.payload)
                    bundle = replace(
                        bundle,
                        triage_reports=[*bundle.triage_reports, triage_report],
                        coverage_ledger=self._update_triaged_ledger(
                            ledger=bundle.coverage_ledger,
                            triage_report=triage_report,
                            proposal_records=proposal_records,
                            state=session.snapshot(),
                        ),
                    )
                    if (
                        not triage_report.survivor_ids
                        and not self._has_expandable_cells(
                            bundle.coverage_ledger,
                            latest_triage_report=triage_report,
                            require_value_gate=False,
                        )
                    ):
                        raise ArgusValidationError(
                            "Research triage eliminated every proposal and left no uncovered cells worth expanding."
                        )
                    self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)
                    self._emit_progress(
                        "stage_completed",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.TRIAGE_PROPOSALS.value,
                            "label": "Triaging proposal families",
                            "nodes": len(session.nodes),
                            "archive": len(session.archive_ids),
                            "frontier": len(session.frontier_ids),
                        },
                    )
                    continue

                if scheduler_decision.action is ResearchSchedulerAction.DEEPEN:
                    current_action = ActionType.DEEPEN_FAMILY.value
                    self._emit_progress(
                        "stage_started",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.DEEPEN_FAMILY.value,
                            "label": "Deepening survivor families",
                            "reason": scheduler_decision.rationale,
                            "target_proposal_ids": list(scheduler_decision.target_proposal_ids),
                        },
                    )
                    deep_dive_responses = self._dispatch_provider_requests(
                        routing_tracker,
                        [
                            _ProviderActionRequest(
                                action_name=ActionType.DEEPEN_FAMILY,
                                problem_spec=session.problem_spec,
                                input_payload=self._deepen_family_payload(
                                    proposal_records[proposal_id],
                                    state=session.snapshot(),
                                    reusable_learning_notes=session.reusable_learning_notes,
                                ),
                                output_schema=deep_dive_doc_schema(),
                            )
                            for proposal_id in scheduler_decision.target_proposal_ids
                        ],
                    )
                    deep_dive_docs = []
                    for response in deep_dive_responses:
                        session.consume_budget()
                        deep_dive_docs.append(response.payload)
                    bundle = replace(
                        bundle,
                        deep_dive_docs=[*bundle.deep_dive_docs, *deep_dive_docs],
                        coverage_ledger=self._update_coverage_status(
                            bundle.coverage_ledger,
                            proposal_ids=[doc.proposal_id for doc in deep_dive_docs],
                            status=CoverageStatus.DEEPENED,
                            note="Deep dive completed.",
                        ),
                    )
                    self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)
                    self._emit_progress(
                        "stage_completed",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.DEEPEN_FAMILY.value,
                            "label": "Deepening survivor families",
                            "nodes": len(session.nodes),
                            "archive": len(session.archive_ids),
                            "frontier": len(session.frontier_ids),
                        },
                    )
                    continue

                if scheduler_decision.action is ResearchSchedulerAction.REDTEAM:
                    current_action = ActionType.REDTEAM_FAMILY.value
                    self._emit_progress(
                        "stage_started",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.REDTEAM_FAMILY.value,
                            "label": "Red-teaming survivors",
                            "reason": scheduler_decision.rationale,
                            "target_proposal_ids": list(scheduler_decision.target_proposal_ids),
                        },
                    )
                    deep_dive_by_proposal = {
                        doc.proposal_id: doc for doc in bundle.deep_dive_docs
                    }
                    review_responses = self._dispatch_provider_requests(
                        routing_tracker,
                        [
                            _ProviderActionRequest(
                                action_name=ActionType.REDTEAM_FAMILY,
                                problem_spec=session.problem_spec,
                                input_payload=self._redteam_payload(
                                    proposal_records[proposal_id],
                                    deep_dive=deep_dive_by_proposal.get(proposal_id),
                                    state=session.snapshot(),
                                    reusable_learning_notes=session.reusable_learning_notes,
                                ),
                                output_schema=adversarial_review_schema(),
                            )
                            for proposal_id in scheduler_decision.target_proposal_ids
                        ],
                    )
                    reviews = []
                    for response in review_responses:
                        session.consume_budget()
                        reviews.append(response.payload)
                    bundle = replace(
                        bundle,
                        adversarial_reviews=[*bundle.adversarial_reviews, *reviews],
                        coverage_ledger=self._update_coverage_status(
                            bundle.coverage_ledger,
                            proposal_ids=[review.proposal_id for review in reviews],
                            status=CoverageStatus.REDTEAMED,
                            note="Adversarial review completed.",
                        ),
                    )
                    self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)
                    self._emit_progress(
                        "stage_completed",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.REDTEAM_FAMILY.value,
                            "label": "Red-teaming survivors",
                            "nodes": len(session.nodes),
                            "archive": len(session.archive_ids),
                            "frontier": len(session.frontier_ids),
                        },
                    )
                    continue

                if scheduler_decision.action is ResearchSchedulerAction.HYBRIDIZE:
                    current_action = ActionType.ASSESS_HYBRID.value
                    self._emit_progress(
                        "stage_started",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.ASSESS_HYBRID.value,
                            "label": "Assessing hybrids",
                            "reason": scheduler_decision.rationale,
                            "target_proposal_ids": list(scheduler_decision.target_proposal_ids),
                        },
                    )
                    hybrid_response = self._run_provider_action(
                        routing_tracker,
                        action_name=ActionType.ASSESS_HYBRID,
                        problem_spec=session.problem_spec,
                        input_payload=self._hybrid_payload(
                            survivor_ids=scheduler_decision.target_proposal_ids,
                            proposal_records=proposal_records,
                            bundle=bundle,
                            reusable_learning_notes=session.reusable_learning_notes,
                        ),
                        output_schema=hybrid_assessment_schema(),
                    )
                    session.consume_budget()
                    bundle = replace(
                        bundle,
                        hybrid_assessments=[*bundle.hybrid_assessments, hybrid_response.payload],
                    )
                    self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)
                    self._emit_progress(
                        "stage_completed",
                        run_id=manifest.run_id,
                        step_count=session.step_count,
                        budget_spent=session.budget_spent,
                        payload={
                            "action": ActionType.ASSESS_HYBRID.value,
                            "label": "Assessing hybrids",
                            "nodes": len(session.nodes),
                            "archive": len(session.archive_ids),
                            "frontier": len(session.frontier_ids),
                        },
                    )
                    continue

            current_action = ActionType.WRITE_FINAL_DECISION.value
            self._emit_progress(
                "stage_started",
                run_id=manifest.run_id,
                step_count=session.step_count,
                budget_spent=session.budget_spent,
                payload={
                    "action": ActionType.WRITE_FINAL_DECISION.value,
                    "label": "Writing final decision",
                    "reason": "Compile the research bundle into a typed final decision package.",
                },
            )
            final_response = self._run_provider_action(
                routing_tracker,
                action_name=ActionType.WRITE_FINAL_DECISION,
                problem_spec=session.problem_spec,
                input_payload=self._final_decision_payload(
                    frame=plan.search_space_frame,
                    bundle=bundle,
                    proposal_records=proposal_records,
                    reusable_learning_notes=session.reusable_learning_notes,
                ),
                output_schema=final_decision_package_schema(),
            )
            session.consume_budget()
            final_package = _validate_final_package(final_response.payload)
            bundle = replace(
                bundle,
                comparison_matrices=[final_package.comparison_matrix],
                final_decision_doc=final_package.final_decision_doc,
                decision_summary_markdown=final_package.decision_summary_markdown,
                decision_report_markdown=final_package.decision_report_markdown,
            )
            learning_notes = _derive_research_learning_notes(bundle)
            session.set_learning_notes(learning_notes)
            recommendation = self._final_recommendation_from_decision(
                bundle=bundle,
                proposal_records=proposal_records,
            )
            session.apply_winners(
                [
                    recommendation.best_bet_node_id,
                    recommendation.conservative_node_id,
                    recommendation.high_upside_node_id,
                ]
            )
            final_state = session.snapshot()
            routing_summary = routing_tracker.build_summary(
                state=final_state,
                run_id=manifest.run_id,
            )
            summary_markdown = recommendation.summary_markdown
            refreshed_manifest = self._state_store.save_snapshot(
                manifest.run_id,
                state=final_state,
                research_bundle=bundle,
                research_markdown=_render_research_bundle_markdown(bundle, proposal_records),
                final_recommendation=recommendation,
                summary_markdown=summary_markdown,
                routing_summary=routing_summary,
                status=RunStatus.COMPLETED,
                metadata_patch={
                    "best_bet_node_id": recommendation.best_bet_node_id,
                    "winner_count": len(final_state.winner_ids),
                    "proposal_count": len(bundle.proposal_briefs),
                },
            )
            if self._reuse_learning_memory and final_state.learning_notes:
                self._state_store.merge_learning_memory(
                    run_id=manifest.run_id,
                    problem_spec=final_state.problem_spec,
                    notes=final_state.learning_notes,
                )
            self._state_store.merge_provider_routing_stats(routing_summary)
            self._emit_progress(
                "run_completed",
                run_id=manifest.run_id,
                step_count=final_state.step_count,
                budget_spent=final_state.budget_spent,
                payload={
                    "best_bet": recommendation.best_bet_node_id,
                    "conservative": recommendation.conservative_node_id,
                    "high_upside": recommendation.high_upside_node_id,
                    "nodes": len(final_state.nodes),
                    "archive": len(final_state.archive_ids),
                    "frontier": len(final_state.frontier_ids),
                },
            )
            return ResearchRunResult(
                run_path=self._state_store.root_dir / refreshed_manifest.run_id,
                manifest=refreshed_manifest,
                state=final_state,
                research_bundle=bundle,
                final_recommendation=recommendation,
                summary_markdown=summary_markdown,
            )
        except Exception as exc:
            failed_state = None if session is None else session.snapshot()
            routing_summary = routing_tracker.build_summary(
                state=failed_state,
                run_id=manifest.run_id,
            )
            if session is None:
                if routing_summary.entries:
                    self._state_store.save_provider_routing_summary(
                        manifest.run_id,
                        routing_summary,
                    )
                self._state_store.update_manifest_status(
                    manifest.run_id,
                    status=RunStatus.FAILED,
                    error=str(exc),
                    metadata_patch={
                        "failure_type": type(exc).__name__,
                        "failed_action": current_action,
                        "runtime_mode": "research",
                    },
                )
            else:
                self._state_store.save_snapshot(
                    manifest.run_id,
                    state=failed_state,
                    research_bundle=bundle if bundle.proposal_briefs or bundle.search_space_frame else None,
                    research_markdown=_render_research_bundle_markdown(bundle, proposal_records)
                    if bundle.proposal_briefs or bundle.search_space_frame
                    else None,
                    routing_summary=routing_summary,
                    status=RunStatus.FAILED,
                    error=str(exc),
                    metadata_patch={
                        "failure_type": type(exc).__name__,
                        "failed_action": current_action,
                        "runtime_mode": "research",
                    },
                )
            if routing_summary.entries:
                self._state_store.merge_provider_routing_stats(routing_summary)
            self._emit_progress(
                "run_failed",
                run_id=manifest.run_id,
                step_count=0 if session is None else session.step_count,
                budget_spent=0 if session is None else session.budget_spent,
                payload={
                    "failure": str(exc),
                    "failed_action": current_action,
                },
            )
            raise
        finally:
            self._action_router = None
            self._active_run_id = ""

    def _build_action_router(self):
        from argus.search.runtime import _ActionRouter

        return _ActionRouter(
            providers=self.providers,
            default_provider_name=self.provider.name,
            routing_stats=self._state_store.load_provider_routing_stats(),
        )

    def _frame_search_space_payload(
        self,
        *,
        problem_spec: ProblemSpec,
        budget: int,
        reusable_learning_notes: Sequence[object],
    ) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "request": problem_spec.request,
            "constraints": list(problem_spec.constraints),
            "success_criteria": list(problem_spec.success_criteria),
            "budget": budget,
            "research_requirements": [
                "Create an explicit search-space frame plus initial coverage ledger.",
                "Focus on materially different candidate families, not quota-driven paraphrases.",
            ],
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _seed_cell_payload(
        self,
        *,
        frame: SearchSpaceFrame,
        ledger: CoverageLedger,
        root_node: Node,
        reusable_learning_notes: Sequence[object],
        target_cells: Sequence[SearchCell] | None = None,
    ) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "frame_id": frame.frame_id,
            "search_space_frame": frame.to_dict(),
            "coverage_ledger": ledger.to_dict(),
            "target_cells": [cell.to_dict() for cell in (ledger.cells if target_cells is None else target_cells)],
            "parent_node_ids": [root_node.node_id],
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _select_scheduler_decision(
        self,
        *,
        bundle: ResearchArtifactBundle,
        proposal_records: Mapping[str, _ResearchProposalRecord],
        remaining_budget: int,
    ) -> SchedulerDecision:
        ledger = bundle.coverage_ledger
        if ledger is None:
            raise ArgusValidationError("coverage ledger must exist before scheduling research actions.")
        latest_triage = None if not bundle.triage_reports else bundle.triage_reports[-1]
        survivor_ids = [] if latest_triage is None else list(latest_triage.survivor_ids)

        candidates: list[tuple[float, int, SchedulerDecision]] = []
        decision_index = len(bundle.scheduler_decisions) + 1

        if remaining_budget >= 3:
            expandable_cells = self._expandable_cells(
                ledger,
                latest_triage_report=latest_triage,
                require_value_gate=latest_triage is not None,
            )
            if expandable_cells:
                target_cell_ids = [cell.cell_id for cell in expandable_cells]
                score = min(
                    1.0,
                    max(self._expand_priority(cell) for cell in expandable_cells)
                    + (0.12 if latest_triage is None else 0.0),
                )
                candidates.append(
                    (
                        score,
                        0,
                        SchedulerDecision(
                            decision_id=f"schedule-{decision_index:03d}",
                            action=ResearchSchedulerAction.EXPAND,
                            rationale=(
                                "Expand coverage because the ledger still has uncovered cells "
                                "whose evidence or uncertainty makes them worth comparing."
                            ),
                            remaining_budget=remaining_budget,
                            priority_score=round(score, 6),
                            target_cell_ids=target_cell_ids,
                            signals=[
                                self._cell_signal(cell)
                                for cell in expandable_cells[: min(3, len(expandable_cells))]
                            ],
                            selected_at=_utcnow(),
                        ),
                    )
                )

        if remaining_budget >= 2 and survivor_ids:
            pending_deepen = self._pending_deepen_ids(
                ledger=ledger,
                survivor_ids=survivor_ids,
                bundle=bundle,
            )
            if pending_deepen:
                target_proposal_ids = pending_deepen[
                    : min(len(pending_deepen), self._max_parallel_targets(remaining_budget))
                ]
                score = max(
                    self._deepen_priority(ledger, proposal_id)
                    for proposal_id in target_proposal_ids
                )
                candidates.append(
                    (
                        score,
                        2,
                        SchedulerDecision(
                            decision_id=f"schedule-{decision_index:03d}",
                            action=ResearchSchedulerAction.DEEPEN,
                            rationale=(
                                "Deepen survivor families whose evidence is promising but whose "
                                "uncertainty is still too high for a final decision."
                            ),
                            remaining_budget=remaining_budget,
                            priority_score=round(score, 6),
                            target_proposal_ids=target_proposal_ids,
                            signals=[
                                self._proposal_signal(ledger, proposal_id)
                                for proposal_id in target_proposal_ids
                            ],
                            selected_at=_utcnow(),
                        ),
                    )
                )

            pending_redteam = self._pending_redteam_ids(
                ledger=ledger,
                survivor_ids=survivor_ids,
                bundle=bundle,
            )
            if pending_redteam:
                target_proposal_ids = pending_redteam[
                    : min(len(pending_redteam), self._max_parallel_targets(remaining_budget))
                ]
                score = max(
                    self._redteam_priority(ledger, proposal_id)
                    for proposal_id in target_proposal_ids
                )
                candidates.append(
                    (
                        score,
                        1,
                        SchedulerDecision(
                            decision_id=f"schedule-{decision_index:03d}",
                            action=ResearchSchedulerAction.REDTEAM,
                            rationale=(
                                "Red-team survivors whose ledger cells still carry material hard-gate "
                                "risk or uncertainty after initial evidence gathering."
                            ),
                            remaining_budget=remaining_budget,
                            priority_score=round(score, 6),
                            target_proposal_ids=target_proposal_ids,
                            signals=[
                                self._proposal_signal(ledger, proposal_id)
                                for proposal_id in target_proposal_ids
                            ],
                            selected_at=_utcnow(),
                        ),
                    )
                )

            hybrid_targets = self._hybrid_target_ids(
                ledger=ledger,
                survivor_ids=survivor_ids,
                bundle=bundle,
            )
            if hybrid_targets:
                score = self._hybrid_priority(ledger, hybrid_targets)
                candidates.append(
                    (
                        score,
                        3,
                        SchedulerDecision(
                            decision_id=f"schedule-{decision_index:03d}",
                            action=ResearchSchedulerAction.HYBRIDIZE,
                            rationale=(
                                "Assess a hybrid only after multiple mature survivors remain and the "
                                "ledger suggests the seam could repair a real failure mode."
                            ),
                            remaining_budget=remaining_budget,
                            priority_score=round(score, 6),
                            target_proposal_ids=hybrid_targets,
                            signals=[
                                self._proposal_signal(ledger, proposal_id)
                                for proposal_id in hybrid_targets
                            ],
                            selected_at=_utcnow(),
                        ),
                    )
                )

        if not candidates:
            return SchedulerDecision(
                decision_id=f"schedule-{decision_index:03d}",
                action=ResearchSchedulerAction.STOP,
                rationale=(
                    "Stop because the remaining budget is reserved for the final decision or the ledger "
                    "no longer shows uncovered, fragile, or insufficiently developed families worth more work."
                ),
                remaining_budget=remaining_budget,
                priority_score=0.0,
                signals=[],
                selected_at=_utcnow(),
            )
        _, _, decision = max(candidates, key=lambda item: (item[0], -item[1]))
        return decision

    def _expandable_cells(
        self,
        ledger: CoverageLedger,
        *,
        latest_triage_report: TriageReport | None,
        require_value_gate: bool,
    ) -> list[SearchCell]:
        unexplored_ids = set() if latest_triage_report is None else set(latest_triage_report.unexplored_cell_ids)
        prioritized = []
        for cell in ledger.cells:
            if cell.coverage_status is not CoverageStatus.UNEXPLORED and cell.cell_id not in unexplored_ids:
                continue
            priority = self._expand_priority(cell)
            if require_value_gate and priority < 0.45:
                continue
            prioritized.append((priority, cell.cell_id, cell))
        prioritized.sort(key=lambda item: (-item[0], item[1]))
        return [cell for _, _, cell in prioritized]

    def _has_expandable_cells(
        self,
        ledger: CoverageLedger | None,
        *,
        latest_triage_report: TriageReport | None,
        require_value_gate: bool,
    ) -> bool:
        if ledger is None:
            return False
        return bool(
            self._expandable_cells(
                ledger,
                latest_triage_report=latest_triage_report,
                require_value_gate=require_value_gate,
            )
        )

    def _cells_for_ids(
        self,
        ledger: CoverageLedger | None,
        cell_ids: Sequence[str],
    ) -> list[SearchCell]:
        if ledger is None:
            raise ArgusValidationError("coverage ledger must exist before selecting target cells.")
        by_id = {cell.cell_id: cell for cell in ledger.cells}
        missing = [cell_id for cell_id in cell_ids if cell_id not in by_id]
        if missing:
            raise ArgusValidationError(
                f"target_cell_ids reference unknown coverage cells: {', '.join(sorted(missing))}."
            )
        return [by_id[cell_id] for cell_id in cell_ids]

    def _proposal_cell(self, ledger: CoverageLedger, proposal_id: str) -> SearchCell:
        for cell in ledger.cells:
            if proposal_id in cell.incumbent_proposal_ids:
                return cell
        raise ArgusValidationError(
            f"coverage ledger does not track an incumbent cell for proposal {proposal_id!r}."
        )

    def _pending_deepen_ids(
        self,
        *,
        ledger: CoverageLedger,
        survivor_ids: Sequence[str],
        bundle: ResearchArtifactBundle,
    ) -> list[str]:
        deepened_ids = {doc.proposal_id for doc in bundle.deep_dive_docs}
        prioritized = []
        for proposal_id in survivor_ids:
            if proposal_id in deepened_ids:
                continue
            priority = self._deepen_priority(ledger, proposal_id)
            prioritized.append((priority, proposal_id))
        prioritized.sort(key=lambda item: (-item[0], item[1]))
        return [proposal_id for priority, proposal_id in prioritized if priority > 0.0]

    def _pending_redteam_ids(
        self,
        *,
        ledger: CoverageLedger,
        survivor_ids: Sequence[str],
        bundle: ResearchArtifactBundle,
    ) -> list[str]:
        deepened_ids = {doc.proposal_id for doc in bundle.deep_dive_docs}
        reviewed_ids = {review.proposal_id for review in bundle.adversarial_reviews}
        prioritized = []
        for proposal_id in survivor_ids:
            if proposal_id not in deepened_ids or proposal_id in reviewed_ids:
                continue
            priority = self._redteam_priority(ledger, proposal_id)
            if priority < 0.2:
                continue
            prioritized.append((priority, proposal_id))
        prioritized.sort(key=lambda item: (-item[0], item[1]))
        return [proposal_id for _, proposal_id in prioritized]

    def _hybrid_target_ids(
        self,
        *,
        ledger: CoverageLedger,
        survivor_ids: Sequence[str],
        bundle: ResearchArtifactBundle,
    ) -> list[str]:
        if bundle.hybrid_assessments:
            return []
        deepened_ids = {doc.proposal_id for doc in bundle.deep_dive_docs}
        reviewed_ids = {review.proposal_id for review in bundle.adversarial_reviews}
        mature_ids = {
            proposal_id
            for proposal_id in survivor_ids
            if proposal_id in deepened_ids and proposal_id in reviewed_ids
        }
        if len(mature_ids) < 2:
            return []
        prioritized = sorted(
            mature_ids,
            key=lambda proposal_id: (
                -self._hybrid_member_priority(ledger, proposal_id),
                proposal_id,
            ),
        )
        return prioritized[:2]

    def _max_parallel_targets(self, remaining_budget: int) -> int:
        reserve_for_final = 1
        return max(
            1,
            min(
                self.policy.provider_max_concurrency,
                max(1, remaining_budget - reserve_for_final),
            ),
        )

    def _expand_priority(self, cell: SearchCell) -> float:
        return round(
            min(
                1.0,
                (0.45 * cell.evidence_strength)
                + (0.35 * cell.uncertainty)
                + (0.20 * cell.hard_gate_risk)
                + (0.08 if not cell.incumbent_proposal_ids else 0.0),
            ),
            6,
        )

    def _deepen_priority(self, ledger: CoverageLedger, proposal_id: str) -> float:
        cell = self._proposal_cell(ledger, proposal_id)
        return round(
            min(
                1.0,
                (0.45 * cell.uncertainty)
                + (0.35 * cell.evidence_strength)
                + (0.20 * (1.0 - cell.hard_gate_risk)),
            ),
            6,
        )

    def _redteam_priority(self, ledger: CoverageLedger, proposal_id: str) -> float:
        cell = self._proposal_cell(ledger, proposal_id)
        return round(
            min(
                1.0,
                (0.50 * cell.hard_gate_risk)
                + (0.30 * cell.uncertainty)
                + (0.20 * cell.evidence_strength),
            ),
            6,
        )

    def _hybrid_member_priority(self, ledger: CoverageLedger, proposal_id: str) -> float:
        cell = self._proposal_cell(ledger, proposal_id)
        return round(
            min(
                1.0,
                (0.50 * cell.evidence_strength)
                + (0.30 * (1.0 - cell.hard_gate_risk))
                + (0.20 * (1.0 - cell.uncertainty)),
            ),
            6,
        )

    def _hybrid_priority(self, ledger: CoverageLedger, proposal_ids: Sequence[str]) -> float:
        member_scores = [self._hybrid_member_priority(ledger, proposal_id) for proposal_id in proposal_ids]
        return round(sum(member_scores) / len(member_scores), 6)

    def _cell_signal(self, cell: SearchCell) -> str:
        return (
            f"{cell.cell_id}: status={cell.coverage_status.value} uncertainty={cell.uncertainty:.2f} "
            f"hard_gate_risk={cell.hard_gate_risk:.2f} evidence_strength={cell.evidence_strength:.2f}"
        )

    def _proposal_signal(self, ledger: CoverageLedger, proposal_id: str) -> str:
        cell = self._proposal_cell(ledger, proposal_id)
        return (
            f"{proposal_id} via {cell.cell_id}: uncertainty={cell.uncertainty:.2f} "
            f"hard_gate_risk={cell.hard_gate_risk:.2f} evidence_strength={cell.evidence_strength:.2f}"
        )

    def _triage_payload(
        self,
        *,
        frame: SearchSpaceFrame,
        ledger: CoverageLedger,
        proposal_records: Mapping[str, _ResearchProposalRecord],
        state: SearchState,
        reusable_learning_notes: Sequence[object],
    ) -> dict[str, JSONValue]:
        proposals = []
        for proposal_id, record in sorted(proposal_records.items()):
            node = state.nodes[record.node_id]
            proposals.append(
                {
                    **record.brief.to_dict(),
                    "node_id": record.node_id,
                    "score": None if node.score is None else node.score.to_dict(),
                    "novelty_score": node.novelty_score,
                    "lifecycle_status": node.lifecycle_status.value,
                    "evaluation": node.metadata.get("evaluation"),
                }
            )
        payload: dict[str, JSONValue] = {
            "frame_id": frame.frame_id,
            "search_space_frame": frame.to_dict(),
            "coverage_ledger": ledger.to_dict(),
            "proposals": proposals,
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _deepen_family_payload(
        self,
        record: _ResearchProposalRecord,
        *,
        state: SearchState,
        reusable_learning_notes: Sequence[object],
    ) -> dict[str, JSONValue]:
        node = state.nodes[record.node_id]
        payload: dict[str, JSONValue] = {
            "proposal": {
                **record.brief.to_dict(),
                "node_id": record.node_id,
                "score": None if node.score is None else node.score.to_dict(),
                "evaluation": node.metadata.get("evaluation"),
            }
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _redteam_payload(
        self,
        record: _ResearchProposalRecord,
        *,
        deep_dive,
        state: SearchState,
        reusable_learning_notes: Sequence[object],
    ) -> dict[str, JSONValue]:
        node = state.nodes[record.node_id]
        payload: dict[str, JSONValue] = {
            "proposal": {
                **record.brief.to_dict(),
                "node_id": record.node_id,
                "score": None if node.score is None else node.score.to_dict(),
                "evaluation": node.metadata.get("evaluation"),
            },
            "deep_dive": None if deep_dive is None else deep_dive.to_dict(),
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _hybrid_payload(
        self,
        *,
        survivor_ids: Sequence[str],
        proposal_records: Mapping[str, _ResearchProposalRecord],
        bundle: ResearchArtifactBundle,
        reusable_learning_notes: Sequence[object],
    ) -> dict[str, JSONValue]:
        proposals = [proposal_records[proposal_id].brief.to_dict() for proposal_id in survivor_ids]
        payload: dict[str, JSONValue] = {
            "source_proposal_ids": list(survivor_ids),
            "proposals": proposals,
            "deep_dives": [
                doc.to_dict()
                for doc in bundle.deep_dive_docs
                if doc.proposal_id in survivor_ids
            ],
            "adversarial_reviews": [
                review.to_dict()
                for review in bundle.adversarial_reviews
                if review.proposal_id in survivor_ids
            ],
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _final_decision_payload(
        self,
        *,
        frame: SearchSpaceFrame,
        bundle: ResearchArtifactBundle,
        proposal_records: Mapping[str, _ResearchProposalRecord],
        reusable_learning_notes: Sequence[object],
    ) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "frame_id": frame.frame_id,
            "search_space_frame": frame.to_dict(),
            "coverage_ledger": None if bundle.coverage_ledger is None else bundle.coverage_ledger.to_dict(),
            "proposals": [
                proposal_records[brief.proposal_id].brief.to_dict()
                for brief in bundle.proposal_briefs
            ],
            "triage_reports": [report.to_dict() for report in bundle.triage_reports],
            "deep_dive_docs": [doc.to_dict() for doc in bundle.deep_dive_docs],
            "adversarial_reviews": [review.to_dict() for review in bundle.adversarial_reviews],
            "hybrid_assessments": [assessment.to_dict() for assessment in bundle.hybrid_assessments],
        }
        if reusable_learning_notes:
            payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        return payload

    def _proposal_admission_request(
        self,
        *,
        brief: ProposalBrief,
        root_id: str,
        provider_name: str,
    ):
        from argus.search.runtime import _CandidateAdmissionRequest

        return _CandidateAdmissionRequest(
            candidate=brief.candidate,
            parent_ids=(root_id,),
            batch_summary=brief.summary,
            source_provider_name=provider_name,
            metadata_patch={
                "proposal_id": brief.proposal_id,
                "proposal_title": brief.title,
                "proposal_cell_id": brief.cell_id,
            },
        )

    def _persist_research_snapshot(
        self,
        run_id: str,
        session: _MutableSession,
        *,
        bundle: ResearchArtifactBundle,
    ) -> None:
        self._state_store.save_snapshot(
            run_id,
            state=session.snapshot(),
            research_bundle=bundle,
            research_markdown=_render_research_bundle_markdown(bundle, {}),
            status=RunStatus.RUNNING,
            metadata_patch={
                "archive_count": len(session.archive_ids),
                "frontier_count": len(session.frontier_ids),
                "pruned_count": len(session.pruned_ids),
                "runtime_mode": "research",
                "proposal_count": len(bundle.proposal_briefs),
            },
        )

    def _update_seeded_ledger(
        self,
        *,
        ledger: CoverageLedger | None,
        proposal_records: Mapping[str, _ResearchProposalRecord],
        state: SearchState,
    ) -> CoverageLedger:
        if ledger is None:
            raise ArgusValidationError("coverage ledger must exist before seeding proposals.")
        cells: list[SearchCell] = []
        for cell in ledger.cells:
            records = [
                record
                for record in proposal_records.values()
                if record.brief.cell_id == cell.cell_id
            ]
            if not records:
                cells.append(cell)
                continue
            node_scores = [
                state.nodes[record.node_id].score
                for record in records
                if state.nodes[record.node_id].score is not None
            ]
            evidence_strength = max(
                [cell.evidence_strength, *[score.total_score / 8.0 for score in node_scores]],
                default=cell.evidence_strength,
            )
            hard_gate_risk = min(
                max(
                    [cell.hard_gate_risk, *[1.0 - score.plausibility for score in node_scores]],
                    default=cell.hard_gate_risk,
                ),
                1.0,
            )
            cells.append(
                replace(
                    cell,
                    coverage_status=CoverageStatus.SEEDED,
                    incumbent_proposal_ids=[record.brief.proposal_id for record in records],
                    evidence_strength=round(evidence_strength, 6),
                    hard_gate_risk=round(hard_gate_risk, 6),
                    uncertainty=round(max(cell.uncertainty * 0.82, 0.1), 6),
                    notes=[*cell.notes, "Representative proposals seeded."],
                )
            )
        return replace(
            ledger,
            cells=cells,
            coverage_summary="Representative proposals now exist for each tracked runtime family.",
            next_questions=["Which seeded family survives triage once evaluation and novelty evidence are considered?"],
            updated_at=_utcnow(),
        )

    def _update_triaged_ledger(
        self,
        *,
        ledger: CoverageLedger | None,
        triage_report: TriageReport,
        proposal_records: Mapping[str, _ResearchProposalRecord],
        state: SearchState,
    ) -> CoverageLedger:
        if ledger is None:
            raise ArgusValidationError("coverage ledger must exist before triage.")
        survivor_ids = set(triage_report.survivor_ids)
        unexplored_cell_ids = set(triage_report.unexplored_cell_ids)
        proposal_by_cell: dict[str, list[str]] = {}
        for proposal_id, record in proposal_records.items():
            proposal_by_cell.setdefault(record.brief.cell_id, []).append(proposal_id)
        cells: list[SearchCell] = []
        for cell in ledger.cells:
            cell_proposal_ids = proposal_by_cell.get(cell.cell_id, [])
            surviving_cell_ids = [proposal_id for proposal_id in cell_proposal_ids if proposal_id in survivor_ids]
            if surviving_cell_ids:
                notes = [*cell.notes, "Family survived triage."]
                if cell.cell_id in unexplored_cell_ids:
                    notes.append("Cell still warrants more expansion after triage.")
                confidence_scores = [
                    state.nodes[proposal_records[proposal_id].node_id].score.confidence_estimate
                    for proposal_id in surviving_cell_ids
                    if state.nodes[proposal_records[proposal_id].node_id].score is not None
                ]
                cells.append(
                    replace(
                        cell,
                        coverage_status=CoverageStatus.TRIAGED,
                        incumbent_proposal_ids=surviving_cell_ids,
                        uncertainty=round(max(0.12, 1.0 - max(confidence_scores, default=0.5)), 6),
                        notes=notes,
                    )
                )
                continue
            if cell.cell_id in unexplored_cell_ids:
                cells.append(
                    replace(
                        cell,
                        coverage_status=CoverageStatus.UNEXPLORED,
                        incumbent_proposal_ids=[],
                        notes=[*cell.notes, "Cell remains insufficiently explored after triage."],
                    )
                )
                continue
            if not cell_proposal_ids:
                cells.append(cell)
                continue
            cells.append(
                replace(
                    cell,
                    coverage_status=CoverageStatus.DOMINATED,
                    incumbent_proposal_ids=[],
                    notes=[*cell.notes, "Family closed during triage."],
                )
            )
        return replace(
            ledger,
            cells=cells,
            coverage_summary=triage_report.summary,
            next_questions=list(triage_report.next_actions),
            updated_at=_utcnow(),
        )

    def _update_coverage_status(
        self,
        ledger: CoverageLedger | None,
        *,
        proposal_ids: Sequence[str],
        status: CoverageStatus,
        note: str,
    ) -> CoverageLedger:
        if ledger is None:
            raise ArgusValidationError("coverage ledger must exist before updating coverage status.")
        proposal_id_set = set(proposal_ids)
        cells = []
        for cell in ledger.cells:
            if not proposal_id_set.intersection(cell.incumbent_proposal_ids):
                cells.append(cell)
                continue
            cells.append(
                replace(
                    cell,
                    coverage_status=status,
                    uncertainty=round(max(0.08, cell.uncertainty * 0.8), 6),
                    notes=[*cell.notes, note],
                )
            )
        return replace(ledger, cells=cells, updated_at=_utcnow())

    def _allocate_survivor_budget(
        self,
        *,
        survivor_ids: Sequence[str],
        remaining_budget: int,
        reserve_for_review: bool,
    ) -> list[str]:
        if remaining_budget <= 1:
            return []
        reserve = 2 if reserve_for_review else 1
        available = max(0, remaining_budget - reserve)
        return list(survivor_ids[: min(len(survivor_ids), max(0, available))])

    def _allocate_review_budget(
        self,
        *,
        survivor_ids: Sequence[str],
        remaining_budget: int,
        reserve_for_hybrid: bool,
    ) -> list[str]:
        if remaining_budget <= 1:
            return []
        reserve = 2 if reserve_for_hybrid else 1
        available = max(0, remaining_budget - reserve)
        return list(survivor_ids[: min(len(survivor_ids), max(0, available))])

    def _final_recommendation_from_decision(
        self,
        *,
        bundle: ResearchArtifactBundle,
        proposal_records: Mapping[str, _ResearchProposalRecord],
    ) -> FinalRecommendation:
        decision = bundle.final_decision_doc
        if decision is None:
            raise ArgusValidationError("final decision document is required.")
        if bundle.decision_summary_markdown is None:
            raise ArgusValidationError("decision summary markdown is required.")
        return FinalRecommendation(
            best_bet_node_id=proposal_records[decision.selected_proposal_id].node_id,
            conservative_node_id=None
            if decision.conservative_proposal_id is None
            else proposal_records[decision.conservative_proposal_id].node_id,
            high_upside_node_id=None
            if decision.high_upside_proposal_id is None
            else proposal_records[decision.high_upside_proposal_id].node_id,
            rejected_but_insightful_ids=[
                proposal_records[proposal_id].node_id
                for proposal_id in decision.rejected_proposal_ids
                if proposal_id in proposal_records
            ],
            summary_markdown=bundle.decision_summary_markdown,
            next_experiments=list(decision.next_experiments),
            assumptions=list(decision.assumptions),
            failure_modes=list(decision.top_risks),
            reversal_conditions=list(decision.reversal_conditions),
        )


def _frame_candidate_from_search_space(frame: SearchSpaceFrame) -> Candidate:
    return Candidate(
        thesis=f"Frame the decision around {frame.target_decision}",
        mechanism=(
            "Use an explicit search-space frame and coverage ledger so Argus can compare "
            "materially different runtime families before writing the final decision."
        ),
        assumptions=list(frame.soft_criteria),
        strengths=list(frame.coverage_plan),
        failure_modes=["The frame could still miss a valuable but unmodeled family."],
        unknowns=list(frame.notes) or ["Whether the selected axes are sufficient."],
        implementation_shape="Coverage-led research runtime with a typed artifact bundle.",
        evidence=[*frame.baseline_options, *frame.hard_gates],
    )


def _validate_search_space_plan(payload: object) -> SearchSpacePlan:
    if not isinstance(payload, SearchSpacePlan):
        raise ArgusValidationError(
            "frame_search_space must return a SearchSpacePlan payload."
        )
    return payload


def _validate_seed_batch(payload: object) -> ProposalSeedBatch:
    if not isinstance(payload, ProposalSeedBatch):
        raise ArgusValidationError(
            "seed_cell_proposals must return a ProposalSeedBatch payload."
        )
    return payload


def _validate_triage_report(payload: object) -> TriageReport:
    if not isinstance(payload, TriageReport):
        raise ArgusValidationError(
            "triage_proposals must return a TriageReport payload."
        )
    return payload


def _validate_final_package(payload: object) -> FinalDecisionPackage:
    if not isinstance(payload, FinalDecisionPackage):
        raise ArgusValidationError(
            "write_final_decision must return a FinalDecisionPackage payload."
        )
    return payload


def _derive_research_learning_notes(bundle: ResearchArtifactBundle) -> list[LearningNote]:
    notes: list[LearningNote] = []
    decision = bundle.final_decision_doc
    if decision is not None:
        notes.append(
            LearningNote(
                note_type=LearningNoteType.WINNING_PATTERN,
                text="Coverage-led planning plus typed decision artifacts produced the strongest default Argus recommendation.",
                source_node_ids=[],
            )
        )
        if decision.top_risks:
            notes.append(
                LearningNote(
                    note_type=LearningNoteType.FAILURE_PATTERN,
                    text=decision.top_risks[0],
                    source_node_ids=[],
                )
            )
    return notes


def _render_research_bundle_markdown(
    bundle: ResearchArtifactBundle,
    proposal_records: Mapping[str, _ResearchProposalRecord],
) -> dict[str, str]:
    markdown: dict[str, str] = {}
    if bundle.search_space_frame is not None:
        markdown["search-space-frame.md"] = _render_frame_markdown(bundle.search_space_frame)
    if bundle.coverage_ledger is not None:
        markdown["coverage-ledger.md"] = _render_ledger_markdown(bundle.coverage_ledger)
    for decision in bundle.scheduler_decisions:
        markdown[f"scheduler/{decision.decision_id}.md"] = _render_scheduler_decision_markdown(decision)
    for brief in bundle.proposal_briefs:
        markdown[f"proposals/{brief.proposal_id}.md"] = _render_proposal_markdown(
            brief,
            proposal_records.get(brief.proposal_id),
        )
    for report in bundle.triage_reports:
        markdown[f"triage/{report.report_id}.md"] = _render_triage_markdown(report)
    for doc in bundle.deep_dive_docs:
        markdown[f"deep-dives/{doc.doc_id}.md"] = _render_deep_dive_markdown(doc)
    for review in bundle.adversarial_reviews:
        markdown[f"reviews/{review.review_id}.md"] = _render_review_markdown(review)
    for matrix in bundle.comparison_matrices:
        markdown[f"comparison/{matrix.matrix_id}.md"] = _render_matrix_markdown(matrix)
    for assessment in bundle.hybrid_assessments:
        markdown[f"hybrids/{assessment.assessment_id}.md"] = _render_hybrid_markdown(assessment)
    if bundle.decision_summary_markdown is not None:
        markdown["decision-summary.md"] = bundle.decision_summary_markdown
    if bundle.final_decision_doc is not None:
        markdown["final-decision.md"] = (
            bundle.decision_report_markdown
            if bundle.decision_report_markdown is not None
            else _render_final_decision_markdown(bundle.final_decision_doc)
        )
    return markdown


def _render_frame_markdown(frame: SearchSpaceFrame) -> str:
    lines = [
        f"# {frame.target_decision}",
        "",
        "## Problem Statement",
        frame.problem_statement,
        "",
        "## Hard Gates",
    ]
    lines.extend(f"- {item}" for item in frame.hard_gates)
    lines.extend(["", "## Soft Criteria"])
    lines.extend(f"- {item}" for item in frame.soft_criteria)
    lines.extend(["", "## Coverage Plan"])
    lines.extend(f"- {item}" for item in frame.coverage_plan)
    return "\n".join(lines).rstrip() + "\n"


def _render_ledger_markdown(ledger: CoverageLedger) -> str:
    lines = ["# Coverage Ledger", "", ledger.coverage_summary, "", "## Cells"]
    for cell in ledger.cells:
        lines.extend(
            [
                f"- `{cell.cell_id}` {cell.label}",
                f"  status={cell.coverage_status.value} uncertainty={cell.uncertainty:.2f} hard_gate_risk={cell.hard_gate_risk:.2f} evidence_strength={cell.evidence_strength:.2f}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_scheduler_decision_markdown(decision: SchedulerDecision) -> str:
    lines = [
        f"# Scheduler Decision {decision.decision_id}",
        "",
        f"- Action: `{decision.action.value}`",
        f"- Remaining budget: {decision.remaining_budget}",
        f"- Priority score: {decision.priority_score:.2f}",
        "",
        decision.rationale,
    ]
    if decision.target_cell_ids:
        lines.extend(["", "## Target Cells"])
        lines.extend(f"- `{cell_id}`" for cell_id in decision.target_cell_ids)
    if decision.target_proposal_ids:
        lines.extend(["", "## Target Proposals"])
        lines.extend(f"- `{proposal_id}`" for proposal_id in decision.target_proposal_ids)
    if decision.signals:
        lines.extend(["", "## Signals"])
        lines.extend(f"- {signal}" for signal in decision.signals)
    return "\n".join(lines).rstrip() + "\n"


def _render_proposal_markdown(
    brief: ProposalBrief,
    record: _ResearchProposalRecord | None,
) -> str:
    lines = [
        f"# {brief.title}",
        "",
        f"Proposal ID: `{brief.proposal_id}`",
        f"Cell ID: `{brief.cell_id}`",
    ]
    if record is not None:
        lines.append(f"Node ID: `{record.node_id}`")
    lines.extend(
        [
            "",
            brief.summary,
            "",
            "## Thesis",
            brief.candidate.thesis,
            "",
            "## Seed Rationale",
            brief.seed_rationale,
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_triage_markdown(report: TriageReport) -> str:
    lines = ["# Triage Report", "", report.summary, "", "## Decisions"]
    for decision in report.decisions:
        lines.append(f"- `{decision.proposal_id}` -> `{decision.disposition.value}`: {decision.rationale}")
    return "\n".join(lines).rstrip() + "\n"


def _render_deep_dive_markdown(doc) -> str:
    lines = [f"# {doc.title}", "", doc.executive_summary, "", "## Implementation Plan"]
    lines.extend(f"- {step}" for step in doc.implementation_plan)
    return "\n".join(lines).rstrip() + "\n"


def _render_review_markdown(review) -> str:
    lines = [f"# Review {review.proposal_id}", "", review.summary, "", "## Failure Modes"]
    lines.extend(f"- {item}" for item in review.failure_modes)
    return "\n".join(lines).rstrip() + "\n"


def _render_matrix_markdown(matrix) -> str:
    lines = ["# Comparison Matrix", "", matrix.summary, "", "## Criteria"]
    lines.extend(f"- {criterion}" for criterion in matrix.criteria)
    return "\n".join(lines).rstrip() + "\n"


def _render_hybrid_markdown(assessment) -> str:
    lines = [f"# {assessment.hybrid_name}", "", assessment.summary, "", "## Seam Hypothesis", assessment.seam_hypothesis]
    return "\n".join(lines).rstrip() + "\n"


def _render_final_decision_markdown(decision) -> str:
    lines = ["# Final Decision", "", decision.summary, "", "## Decision Rule", decision.decision_rule]
    lines.extend(["", "## Next Experiments"])
    lines.extend(f"- {item}" for item in decision.next_experiments)
    return "\n".join(lines).rstrip() + "\n"
