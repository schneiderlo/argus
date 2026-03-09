from __future__ import annotations

from dataclasses import replace

from argus.errors import ArgusValidationError
from argus.models import (
    ActionType,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ResearchArtifactBundle,
)
from argus.models.research import CoverageStatus
from argus.search.research_contracts import (
    deep_dive_doc_schema,
    final_decision_package_schema,
    proposal_seed_batch_schema,
    search_space_plan_schema,
    triage_report_schema,
)
from argus.search.research_runtime import (
    ResearchRunResult,
    ResearchRuntime,
    _ResearchProposalRecord,
    _derive_research_learning_notes,
    _frame_candidate_from_search_space,
    _render_research_bundle_markdown,
    _validate_final_package,
    _validate_search_space_plan,
    _validate_seed_batch,
    _validate_triage_report,
)
from argus.search.runtime import (
    _MutableSession,
    _ProviderActionRequest,
    _RoutingTracker,
    _evaluation_metadata,
    _provider_routing_metadata,
    _utcnow,
    balanced_island_policy,
)
from argus.storage import RunStatus


class StagedResearchRuntime(ResearchRuntime):
    """Benchmark-only staged research baseline with a fixed 5-step pipeline."""

    _MIN_STAGED_BUDGET = 5

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
        if not isinstance(budget, int) or budget < self._MIN_STAGED_BUDGET:
            raise ArgusValidationError(
                f"staged runtime requires budget >= {self._MIN_STAGED_BUDGET}."
            )

        initial_problem_spec = ProblemSpec(
            request=problem_spec.request,
            constraints=list(problem_spec.constraints),
            success_criteria=list(problem_spec.success_criteria),
            context={
                **problem_spec.context,
                "requested_provider": self.provider.name,
                "provider_pool": list(self.providers),
                "runtime_mode": "staged",
            },
        )
        self._action_router = self._build_action_router()
        manifest = self._state_store.create_run(
            problem_spec=initial_problem_spec,
            provider_name=self.provider.name,
            budget=budget,
            run_id=run_id,
            metadata={
                "runtime": "research_staged_v1",
                "runtime_mode": "staged",
                "provider_pool": list(self.providers),
                "search_profile": "research_staged",
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
                "runtime_mode": "staged",
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
            self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)

            current_action = ActionType.SEED_CELL_PROPOSALS.value
            seed_response = self._run_provider_action(
                routing_tracker,
                action_name=ActionType.SEED_CELL_PROPOSALS,
                problem_spec=session.problem_spec,
                input_payload=self._seed_cell_payload(
                    frame=plan.search_space_frame,
                    ledger=plan.coverage_ledger,
                    root_node=root_node,
                    reusable_learning_notes=session.reusable_learning_notes,
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
            proposal_records = {
                brief.proposal_id: _ResearchProposalRecord(brief=brief, node_id=node.node_id)
                for brief, node in zip(seeded_batch.proposals, admitted_nodes)
            }
            bundle = replace(
                bundle,
                proposal_briefs=list(seeded_batch.proposals),
                coverage_ledger=self._update_seeded_ledger(
                    ledger=bundle.coverage_ledger,
                    proposal_records=proposal_records,
                    state=session.snapshot(),
                ),
            )
            session.refresh_frontier(limit=max(2, self.policy.frontier_limit))
            self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)

            current_action = ActionType.TRIAGE_PROPOSALS.value
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
                triage_reports=[triage_report],
                coverage_ledger=self._update_triaged_ledger(
                    ledger=bundle.coverage_ledger,
                    triage_report=triage_report,
                    proposal_records=proposal_records,
                    state=session.snapshot(),
                ),
            )
            self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)

            survivor_ids = list(triage_report.survivor_ids)
            if not survivor_ids:
                raise ArgusValidationError("Staged triage eliminated every proposal; no survivor remained.")

            deep_dive_ids = self._allocate_survivor_budget(
                survivor_ids=survivor_ids,
                remaining_budget=budget - session.budget_spent,
                reserve_for_review=False,
            )
            if deep_dive_ids:
                current_action = ActionType.DEEPEN_FAMILY.value
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
                        for proposal_id in deep_dive_ids
                    ],
                )
                deep_dive_docs = []
                for response in deep_dive_responses:
                    session.consume_budget()
                    deep_dive_docs.append(response.payload)
                bundle = replace(
                    bundle,
                    deep_dive_docs=deep_dive_docs,
                    coverage_ledger=self._update_coverage_status(
                        bundle.coverage_ledger,
                        proposal_ids=[doc.proposal_id for doc in deep_dive_docs],
                        status=CoverageStatus.DEEPENED,
                        note="Deep dive completed.",
                    ),
                )
                self._persist_research_snapshot(manifest.run_id, session, bundle=bundle)

            current_action = ActionType.WRITE_FINAL_DECISION.value
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
                    "runtime_mode": "staged",
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
                    "runtime_mode": "staged",
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
                        "runtime_mode": "staged",
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
                        "runtime_mode": "staged",
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
