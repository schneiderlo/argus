from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from argus.errors import ArgusValidationError
from argus.eval import AgenticEvaluator, AgenticNoveltyFilter, rank_nodes
from argus.models import (
    ActionType,
    Candidate,
    FinalRecommendation,
    JSONValue,
    LearningNote,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    SearchState,
)
from argus.providers import Provider
from argus.search.contracts import (
    ProblemFrame,
    candidate_batch_schema,
    candidate_schema,
    critique_schema,
    learning_compression_schema,
    problem_frame_schema,
)
from argus.storage import FileSystemStateStore, RunManifest, RunStatus


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    seed_target: int = 8
    stress_test_limit: int = 5
    deepen_limit: int = 3
    mutate_limit: int = 1
    combine_limit: int = 1
    frontier_limit: int = 6
    rejected_limit: int = 3
    max_learning_notes: int = 4

    def __post_init__(self) -> None:
        for field_name in (
            "seed_target",
            "stress_test_limit",
            "deepen_limit",
            "mutate_limit",
            "combine_limit",
            "frontier_limit",
            "rejected_limit",
            "max_learning_notes",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value <= 0:
                raise ArgusValidationError(f"{field_name} must be a positive integer.")

    def to_dict(self) -> dict[str, int]:
        return {
            "seed_target": self.seed_target,
            "stress_test_limit": self.stress_test_limit,
            "deepen_limit": self.deepen_limit,
            "mutate_limit": self.mutate_limit,
            "combine_limit": self.combine_limit,
            "frontier_limit": self.frontier_limit,
            "rejected_limit": self.rejected_limit,
            "max_learning_notes": self.max_learning_notes,
        }


@dataclass(frozen=True, slots=True)
class SearchRunResult:
    run_path: Path
    manifest: RunManifest
    state: SearchState
    final_recommendation: FinalRecommendation
    summary_markdown: str


class SearchRuntime:
    def __init__(
        self,
        *,
        provider: Provider,
        state_store: FileSystemStateStore,
        policy: SearchPolicy | None = None,
    ) -> None:
        self._provider = provider
        self._state_store = state_store
        self._policy = policy or SearchPolicy()
        self._evaluator = AgenticEvaluator(provider=provider)
        self._novelty_filter = AgenticNoveltyFilter(provider=provider)

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def policy(self) -> SearchPolicy:
        return self._policy

    def run(
        self,
        *,
        request: str,
        budget: int,
        run_id: str | None = None,
    ) -> SearchRunResult:
        normalized_request = _normalize_non_empty_string(request, "request")
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
    ) -> SearchRunResult:
        if not isinstance(problem_spec, ProblemSpec):
            raise ArgusValidationError(
                "problem_spec must be a ProblemSpec instance, "
                f"got {type(problem_spec).__name__}."
            )
        if not isinstance(budget, int) or budget <= 0:
            raise ArgusValidationError("budget must be a positive integer.")

        initial_problem_spec = ProblemSpec(
            request=problem_spec.request,
            constraints=list(problem_spec.constraints),
            success_criteria=list(problem_spec.success_criteria),
            context={
                **problem_spec.context,
                "requested_provider": self._provider.name,
            },
        )
        manifest = self._state_store.create_run(
            problem_spec=initial_problem_spec,
            provider_name=self._provider.name,
            budget=budget,
            run_id=run_id,
            metadata={"runtime": "search_v1"},
        )

        session: _MutableSession | None = None
        routing_tracker = _RoutingTracker(default_provider_name=self._provider.name)
        current_action = ActionType.FRAME_PROBLEM.value
        try:
            frame = self._frame_problem(initial_problem_spec, budget, routing_tracker)
            root_node = self._build_framing_node(frame)
            session = _MutableSession(
                problem_spec=frame.problem_spec,
                root_node=root_node,
                budget_spent=1,
                step_count=1,
            )
            session.set_learning_notes([])
            session.refresh_frontier(limit=self._policy.frontier_limit)
            self._persist_running_snapshot(manifest.run_id, session, frame_summary=frame.framing_notes)

            if session.budget_spent < budget:
                current_action = ActionType.GENERATE_SEED.value
                self._generate_seed_nodes(session, routing_tracker)
                self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            session.refresh_frontier(limit=self._policy.frontier_limit)

            current_action = ActionType.STRESS_TEST.value
            self._stress_test_frontier(session, budget, routing_tracker)
            self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            session.refresh_frontier(limit=self._policy.frontier_limit)

            current_action = ActionType.DEEPEN.value
            self._deepen_frontier(session, budget, routing_tracker)
            self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            session.refresh_frontier(limit=self._policy.frontier_limit)

            current_action = ActionType.MUTATE.value
            self._mutate_survivors(session, budget, routing_tracker)

            current_action = ActionType.COMBINE.value
            self._combine_survivors(session, budget, routing_tracker)
            self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.COMPRESS_LEARNING.value
            self._compress_learning(session, budget, routing_tracker)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            recommendation = self._compile_final_recommendation(session.snapshot())
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
                final_recommendation=recommendation,
                summary_markdown=summary_markdown,
                routing_summary=routing_summary,
                status=RunStatus.COMPLETED,
                metadata_patch={
                    "best_bet_node_id": recommendation.best_bet_node_id,
                    "winner_count": len(final_state.winner_ids),
                },
            )
            self._state_store.merge_provider_routing_stats(routing_summary)
            return SearchRunResult(
                run_path=self._state_store.root_dir / refreshed_manifest.run_id,
                manifest=refreshed_manifest,
                state=final_state,
                final_recommendation=recommendation,
                summary_markdown=summary_markdown,
            )
        except Exception as exc:
            failure_metadata = {
                "failure_type": type(exc).__name__,
                "failed_action": current_action,
            }
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
                    metadata_patch=failure_metadata,
                )
            else:
                self._state_store.save_snapshot(
                    manifest.run_id,
                    state=failed_state,
                    routing_summary=routing_summary,
                    status=RunStatus.FAILED,
                    error=str(exc),
                    metadata_patch=failure_metadata,
                )
            if routing_summary.entries:
                self._state_store.merge_provider_routing_stats(routing_summary)
            raise

    def _frame_problem(
        self,
        problem_spec: ProblemSpec,
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> ProblemFrame:
        response = self._run_provider_action(
            routing_tracker,
            action_name=ActionType.FRAME_PROBLEM,
            problem_spec=problem_spec,
            input_payload={
                "request": problem_spec.request,
                "budget": budget,
                "search_policy": self._policy.to_dict(),
                "framing_requirements": [
                    "Normalize explicit constraints.",
                    "Normalize success criteria.",
                    "Produce a framing candidate that captures the most decision-relevant angle.",
                ],
            },
            output_schema=problem_frame_schema(),
        )
        return response.payload

    def _build_framing_node(self, frame: ProblemFrame) -> Node:
        assessment = self._evaluator.evaluate(
            frame.problem_spec,
            frame.framing_candidate,
            novelty_score=1.0,
        )
        return Node(
            node_id="node-0001",
            parent_ids=[],
            depth=0,
            action_type=ActionType.FRAME_PROBLEM,
            provider_name=self._provider.name,
            candidate=frame.framing_candidate,
            score=assessment.score,
            novelty_score=1.0,
            lifecycle_status=NodeLifecycleStatus.ADMITTED,
            metadata={
                "framing_notes": list(frame.framing_notes),
                "evaluation": _evaluation_metadata(assessment),
            },
            created_at=_utcnow(),
        )

    def _generate_seed_nodes(
        self,
        session: "_MutableSession",
        routing_tracker: "_RoutingTracker",
    ) -> None:
        response = self._run_provider_action(
            routing_tracker,
            action_name=ActionType.GENERATE_SEED,
            problem_spec=session.problem_spec,
            input_payload={
                "target_count": self._policy.seed_target,
                "framing_candidate": session.root_node.candidate.to_dict(),
                "learning_notes": [note.to_dict() for note in session.learning_notes],
                "generation_policy": {
                    "diversity_requirement": (
                        "Return materially distinct strategic directions, not paraphrases."
                    ),
                    "quality_requirement": (
                        "Prefer executable mechanisms with explicit assumptions and failure modes."
                    ),
                },
            },
            output_schema=candidate_batch_schema(),
        )
        session.consume_budget()
        batch = response.payload
        for candidate in batch.candidates:
            self._admit_candidate(
                session,
                action_type=ActionType.GENERATE_SEED,
                candidate=candidate,
                parent_ids=[session.root_id],
                batch_summary=batch.batch_summary,
            )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _stress_test_frontier(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        for node in self._top_ranked_nodes(session, limit=self._policy.stress_test_limit):
            if session.budget_spent >= budget:
                break
            response = self._run_provider_action(
                routing_tracker,
                action_name=ActionType.STRESS_TEST,
                problem_spec=session.problem_spec,
                input_payload={
                    "node_id": node.node_id,
                    "candidate": node.candidate.to_dict(),
                    "score": None if node.score is None else node.score.to_dict(),
                    "learning_notes": [note.to_dict() for note in session.learning_notes],
                    "stress_test_policy": {
                        "focus": [
                            "hidden dependencies",
                            "kill shots",
                            "operational sharp edges",
                        ],
                    },
                },
                output_schema=critique_schema(),
            )
            session.consume_budget()
            critique = response.payload
            routing_tracker.record_critique(
                action_name=ActionType.STRESS_TEST.value,
                provider_name=self._provider.name,
                useful=_is_useful_critique(critique),
            )
            updated = replace(
                node,
                critique=critique,
                metadata={
                    **node.metadata,
                    "stress_test": critique.to_dict(),
                },
            )
            session.replace_node(updated)

    def _deepen_frontier(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        for node in self._top_ranked_nodes(session, limit=self._policy.deepen_limit):
            if session.budget_spent >= budget:
                break
            response = self._run_provider_action(
                routing_tracker,
                action_name=ActionType.DEEPEN,
                problem_spec=session.problem_spec,
                input_payload={
                    "node_id": node.node_id,
                    "candidate": node.candidate.to_dict(),
                    "score": None if node.score is None else node.score.to_dict(),
                    "critique": None if node.critique is None else node.critique.to_dict(),
                    "learning_notes": [note.to_dict() for note in session.learning_notes],
                    "deepen_policy": {
                        "goal": (
                            "Increase specificity and execution readiness without collapsing distinctiveness."
                        ),
                    },
                },
                output_schema=candidate_schema(),
            )
            session.consume_budget()
            self._admit_candidate(
                session,
                action_type=ActionType.DEEPEN,
                candidate=response.payload,
                parent_ids=[node.node_id],
                batch_summary="Deepened a high-scoring survivor.",
            )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _mutate_survivors(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        mutations = 0
        for node in self._top_ranked_nodes(session, limit=self._policy.mutate_limit):
            if mutations >= self._policy.mutate_limit or session.budget_spent >= budget:
                break
            response = self._run_provider_action(
                routing_tracker,
                action_name=ActionType.MUTATE,
                problem_spec=session.problem_spec,
                input_payload={
                    "node_id": node.node_id,
                    "candidate": node.candidate.to_dict(),
                    "score": None if node.score is None else node.score.to_dict(),
                    "critique": None if node.critique is None else node.critique.to_dict(),
                    "mutation_policy": {
                        "goal": "Address the sharpest weakness while preserving the core mechanism.",
                    },
                },
                output_schema=candidate_batch_schema(),
            )
            session.consume_budget()
            mutations += 1
            for candidate in response.payload.candidates:
                self._admit_candidate(
                    session,
                    action_type=ActionType.MUTATE,
                    candidate=candidate,
                    parent_ids=[node.node_id],
                    batch_summary=response.payload.batch_summary,
                )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _combine_survivors(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        if self._policy.combine_limit <= 0 or session.budget_spent >= budget:
            return
        ranked = self._top_ranked_nodes(session, limit=2)
        if len(ranked) < 2:
            return
        response = self._run_provider_action(
            routing_tracker,
            action_name=ActionType.COMBINE,
            problem_spec=session.problem_spec,
            input_payload={
                "primary_node_id": ranked[0].node_id,
                "secondary_node_id": ranked[1].node_id,
                "primary_candidate": ranked[0].candidate.to_dict(),
                "secondary_candidate": ranked[1].candidate.to_dict(),
                "combine_policy": {
                    "goal": (
                        "Fuse compatible strengths only if the combined direction remains coherent and distinct."
                    ),
                },
            },
            output_schema=candidate_batch_schema(),
        )
        session.consume_budget()
        for candidate in response.payload.candidates:
            self._admit_candidate(
                session,
                action_type=ActionType.COMBINE,
                candidate=candidate,
                parent_ids=[ranked[0].node_id, ranked[1].node_id],
                batch_summary=response.payload.batch_summary,
            )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _compress_learning(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        if session.budget_spent >= budget:
            return

        archived_nodes = [
            _node_snapshot_payload(session.nodes[node_id])
            for node_id in session.archive_ids[: self._policy.frontier_limit]
        ]
        pruned_nodes = [
            _node_snapshot_payload(session.nodes[node_id])
            for node_id in session.pruned_ids[: self._policy.rejected_limit]
        ]
        if not archived_nodes and not pruned_nodes:
            return

        response = self._run_provider_action(
            routing_tracker,
            action_name=ActionType.COMPRESS_LEARNING,
            problem_spec=session.problem_spec,
            input_payload={
                "archived_nodes": archived_nodes,
                "pruned_nodes": pruned_nodes,
                "max_notes": self._policy.max_learning_notes,
                "compression_policy": {
                    "goal": "Extract reusable patterns, failure modes, and constraints from the current search state.",
                },
            },
            output_schema=learning_compression_schema(),
        )
        session.consume_budget()
        compression = response.payload
        routing_tracker.record_learning_notes(
            action_name=ActionType.COMPRESS_LEARNING.value,
            provider_name=self._provider.name,
            count=len(compression.notes),
        )
        session.set_learning_notes(compression.notes[: self._policy.max_learning_notes])
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _run_provider_action(
        self,
        routing_tracker: "_RoutingTracker",
        *,
        action_name: ActionType | str,
        problem_spec: ProblemSpec,
        input_payload,
        output_schema,
    ):
        normalized_action = action_name.value if isinstance(action_name, ActionType) else action_name
        routing_tracker.record_invocation(
            action_name=normalized_action,
            provider_name=self._provider.name,
        )
        try:
            return self._provider.run_action(
                action_name=action_name,
                problem_spec=problem_spec,
                input_payload=input_payload,
                output_schema=output_schema,
            )
        except Exception:
            routing_tracker.record_provider_failure(
                action_name=normalized_action,
                provider_name=self._provider.name,
            )
            raise

    def _admit_candidate(
        self,
        session: "_MutableSession",
        *,
        action_type: ActionType,
        candidate: Candidate,
        parent_ids: Sequence[str],
        batch_summary: str,
    ) -> Node:
        archive_nodes = [session.nodes[node_id] for node_id in session.archive_ids]
        novelty = self._novelty_filter.assess(
            problem_spec=session.problem_spec,
            candidate=candidate,
            archive_nodes=archive_nodes,
        )
        assessment = self._evaluator.evaluate(
            session.problem_spec,
            candidate,
            novelty_score=novelty.novelty_score,
        )
        node_id = session.allocate_node_id()
        if parent_ids:
            depth = max(session.nodes[parent_id].depth for parent_id in parent_ids) + 1
        else:
            depth = 0

        metadata: dict[str, JSONValue] = {
            "batch_summary": batch_summary,
            "novelty": novelty.to_dict(),
            "evaluation": _evaluation_metadata(assessment),
        }
        if not novelty.is_novel:
            lifecycle_status = NodeLifecycleStatus.REJECTED
        elif not assessment.score.hard_constraint_pass:
            lifecycle_status = NodeLifecycleStatus.FAILED
        else:
            lifecycle_status = NodeLifecycleStatus.ADMITTED

        node = Node(
            node_id=node_id,
            parent_ids=list(parent_ids),
            depth=depth,
            action_type=action_type,
            provider_name=self._provider.name,
            candidate=candidate,
            score=assessment.score,
            novelty_score=novelty.novelty_score,
            lifecycle_status=lifecycle_status,
            metadata=metadata,
            created_at=_utcnow(),
        )
        session.add_node(node)
        if lifecycle_status is NodeLifecycleStatus.REJECTED:
            return node
        if lifecycle_status is NodeLifecycleStatus.FAILED:
            session.mark_pruned(node.node_id)
            return node
        session.archive(node.node_id)
        return node

    def _top_ranked_nodes(
        self,
        session: "_MutableSession",
        *,
        limit: int,
    ) -> list[Node]:
        eligible = [
            session.nodes[node_id]
            for node_id in session.frontier_ids
            if _is_rankable(session.nodes[node_id])
        ]
        if not eligible:
            eligible = [
                node
                for node_id, node in session.nodes.items()
                if node_id in session.archive_ids and _is_rankable(node)
            ]
        if not eligible:
            return []
        return rank_nodes(eligible)[:limit]

    def _persist_running_snapshot(
        self,
        run_id: str,
        session: "_MutableSession",
        *,
        frame_summary: Sequence[str] | None = None,
    ) -> None:
        metadata_patch: dict[str, JSONValue] = {
            "archive_count": len(session.archive_ids),
            "frontier_count": len(session.frontier_ids),
            "pruned_count": len(session.pruned_ids),
        }
        if frame_summary is not None:
            metadata_patch["frame_summary"] = list(frame_summary)
        self._state_store.save_snapshot(
            run_id,
            state=session.snapshot(),
            status=RunStatus.RUNNING,
            metadata_patch=metadata_patch,
        )

    def _compile_final_recommendation(self, state: SearchState) -> FinalRecommendation:
        candidates = _finalist_nodes(state)
        if not candidates:
            raise ArgusValidationError("Cannot compile a final recommendation without any viable nodes.")

        best = rank_nodes(candidates)[0]
        conservative = _select_distinct_candidate(
            candidates,
            excluded_ids={best.node_id},
            key=lambda node: (
                node.score.implementation_tractability,
                node.score.plausibility,
                node.score.adversarial_robustness,
                node.score.confidence_estimate,
                node.score.total_score,
            ),
        )
        if conservative is None:
            conservative = best

        high_upside = _select_distinct_candidate(
            candidates,
            excluded_ids={best.node_id, conservative.node_id},
            key=lambda node: (
                node.score.upside,
                node.novelty_score,
                node.score.distinctiveness,
                node.score.total_score,
                node.score.confidence_estimate,
            ),
        )
        if high_upside is None:
            high_upside = best

        rejected = _select_rejected_nodes(state, limit=self._policy.rejected_limit)
        assumptions = _collect_unique_strings(
            [
                *best.candidate.assumptions,
                *conservative.candidate.assumptions,
                *high_upside.candidate.assumptions,
            ],
            limit=6,
        )
        failure_modes = _collect_unique_strings(
            [
                *best.candidate.failure_modes,
                *conservative.candidate.failure_modes,
                *high_upside.candidate.failure_modes,
                *(best.critique.kill_shots if best.critique is not None else []),
                *(best.critique.sharp_edges if best.critique is not None else []),
            ],
            limit=8,
        )
        next_experiments = _build_next_experiments(best)
        reversal_conditions = _collect_unique_strings(
            [
                *(best.critique.kill_shots if best.critique is not None else []),
                *(best.critique.hidden_dependencies if best.critique is not None else []),
                *best.candidate.unknowns,
            ],
            limit=5,
        )
        summary_markdown = _render_summary_markdown(
            problem_spec=state.problem_spec,
            best=best,
            conservative=conservative,
            high_upside=high_upside,
            rejected=rejected,
            learning_notes=state.learning_notes,
            next_experiments=next_experiments,
            assumptions=assumptions,
            failure_modes=failure_modes,
            reversal_conditions=reversal_conditions,
        )
        return FinalRecommendation(
            best_bet_node_id=best.node_id,
            conservative_node_id=conservative.node_id,
            high_upside_node_id=high_upside.node_id,
            rejected_but_insightful_ids=[node.node_id for node in rejected],
            summary_markdown=summary_markdown,
            next_experiments=next_experiments,
            assumptions=assumptions,
            failure_modes=failure_modes,
            reversal_conditions=reversal_conditions,
        )


class _MutableSession:
    def __init__(
        self,
        *,
        problem_spec: ProblemSpec,
        root_node: Node,
        budget_spent: int,
        step_count: int,
    ) -> None:
        self.problem_spec = problem_spec
        self.root_id = root_node.node_id
        self.nodes: dict[str, Node] = {root_node.node_id: root_node}
        self.archive_ids: list[str] = [root_node.node_id]
        self.frontier_ids: list[str] = [root_node.node_id]
        self.pruned_ids: list[str] = []
        self.winner_ids: list[str] = []
        self.learning_notes: list[LearningNote] = []
        self.budget_spent = budget_spent
        self.step_count = step_count
        self._next_node_index = 2

    @property
    def root_node(self) -> Node:
        return self.nodes[self.root_id]

    def allocate_node_id(self) -> str:
        while True:
            candidate = f"node-{self._next_node_index:04d}"
            self._next_node_index += 1
            if candidate not in self.nodes:
                return candidate

    def consume_budget(self) -> None:
        self.budget_spent += 1
        self.step_count += 1

    def record_internal_step(self) -> None:
        self.step_count += 1

    def add_node(self, node: Node) -> None:
        self.nodes[node.node_id] = node

    def replace_node(self, node: Node) -> None:
        self.nodes[node.node_id] = node

    def archive(self, node_id: str) -> None:
        _append_unique(self.archive_ids, node_id)

    def mark_pruned(self, node_id: str) -> None:
        _append_unique(self.pruned_ids, node_id)

    def set_learning_notes(self, notes: Sequence[LearningNote]) -> None:
        self.learning_notes = list(notes)

    def refresh_frontier(self, *, limit: int) -> None:
        candidates = [
            node
            for node_id, node in self.nodes.items()
            if node_id in self.archive_ids and _is_rankable(node)
        ]
        if not candidates:
            self.frontier_ids = [self.root_id]
            return

        ranked = rank_nodes(candidates)
        frontier: list[str] = []
        for node in ranked[:limit]:
            _append_unique(frontier, node.node_id)

        most_novel = max(candidates, key=lambda node: (node.novelty_score, node.score.total_score))
        _append_unique(frontier, most_novel.node_id)

        most_uncertain = min(
            candidates,
            key=lambda node: (node.score.confidence_estimate, -node.novelty_score),
        )
        _append_unique(frontier, most_uncertain.node_id)
        self.frontier_ids = frontier[:limit]

        for node_id, node in list(self.nodes.items()):
            if node.lifecycle_status in {
                NodeLifecycleStatus.REJECTED,
                NodeLifecycleStatus.FAILED,
                NodeLifecycleStatus.PRUNED,
                NodeLifecycleStatus.WINNER,
            }:
                continue
            status = (
                NodeLifecycleStatus.ADMITTED
                if node_id in self.frontier_ids
                else NodeLifecycleStatus.ARCHIVED
            )
            self.nodes[node_id] = replace(node, lifecycle_status=status)

    def apply_winners(self, node_ids: Iterable[str | None]) -> None:
        self.winner_ids = []
        for node_id in node_ids:
            if node_id is None:
                continue
            _append_unique(self.winner_ids, node_id)
            node = self.nodes[node_id]
            self.nodes[node_id] = replace(node, lifecycle_status=NodeLifecycleStatus.WINNER)

    def snapshot(self) -> SearchState:
        return SearchState(
            problem_spec=self.problem_spec,
            root_id=self.root_id,
            nodes=dict(sorted(self.nodes.items())),
            archive_ids=list(self.archive_ids),
            frontier_ids=list(self.frontier_ids),
            pruned_ids=list(self.pruned_ids),
            winner_ids=list(self.winner_ids),
            learning_notes=list(self.learning_notes),
            budget_spent=self.budget_spent,
            step_count=self.step_count,
        )


@dataclass(slots=True)
class _RoutingAccumulator:
    run_count: int = 0
    invocation_count: int = 0
    provider_failure_count: int = 0
    candidate_count: int = 0
    scored_node_count: int = 0
    admitted_count: int = 0
    rejected_count: int = 0
    hard_fail_count: int = 0
    strong_score_count: int = 0
    stress_test_survivor_count: int = 0
    winner_count: int = 0
    winner_contribution_count: int = 0
    critique_count: int = 0
    useful_critique_count: int = 0
    learning_note_count: int = 0
    accumulated_score: float = 0.0

    def total_reward(self) -> float:
        return (
            self.admitted_count * 1.0
            + self.strong_score_count * 0.75
            + self.stress_test_survivor_count * 1.25
            + self.winner_contribution_count * 2.0
            + self.useful_critique_count * 1.0
            + self.learning_note_count * 0.25
            - self.rejected_count * 0.5
            - self.hard_fail_count * 1.0
            - self.provider_failure_count * 2.0
        )


class _RoutingTracker:
    def __init__(self, *, default_provider_name: str) -> None:
        self._default_provider_name = _normalize_non_empty_string(
            default_provider_name,
            "default_provider_name",
        )
        self._invocations: dict[tuple[str, str], int] = defaultdict(int)
        self._provider_failures: dict[tuple[str, str], int] = defaultdict(int)
        self._critiques: dict[tuple[str, str], tuple[int, int]] = {}
        self._learning_note_counts: dict[tuple[str, str], int] = defaultdict(int)

    def record_invocation(self, *, action_name: str, provider_name: str | None = None) -> None:
        self._invocations[self._key(action_name, provider_name)] += 1

    def record_provider_failure(
        self,
        *,
        action_name: str,
        provider_name: str | None = None,
    ) -> None:
        self._provider_failures[self._key(action_name, provider_name)] += 1

    def record_critique(
        self,
        *,
        action_name: str,
        provider_name: str | None = None,
        useful: bool,
    ) -> None:
        key = self._key(action_name, provider_name)
        critique_count, useful_count = self._critiques.get(key, (0, 0))
        self._critiques[key] = (
            critique_count + 1,
            useful_count + (1 if useful else 0),
        )

    def record_learning_notes(
        self,
        *,
        action_name: str,
        provider_name: str | None = None,
        count: int,
    ) -> None:
        if not isinstance(count, int) or count < 0:
            raise ArgusValidationError("count must be a non-negative integer.")
        self._learning_note_counts[self._key(action_name, provider_name)] += count

    def build_summary(
        self,
        *,
        state: SearchState | None,
        run_id: str,
    ) -> ProviderRoutingStats:
        normalized_run_id = _normalize_non_empty_string(run_id, "run_id")
        updated_at = _utcnow()
        accumulators: dict[tuple[str, str], _RoutingAccumulator] = defaultdict(_RoutingAccumulator)
        for key in self._all_keys(state):
            accumulators[key].run_count = 1

        for key, count in self._invocations.items():
            accumulators[key].invocation_count += count
        for key, count in self._provider_failures.items():
            accumulators[key].provider_failure_count += count
        for key, (critique_count, useful_count) in self._critiques.items():
            accumulators[key].critique_count += critique_count
            accumulators[key].useful_critique_count += useful_count
        for key, count in self._learning_note_counts.items():
            accumulators[key].learning_note_count += count

        if state is not None:
            winner_contributors = _winner_contributor_ids(state)
            stress_test_survivors = _stress_test_survivor_ids(state, winner_contributors)
            for node in state.nodes.values():
                key = (node.provider_name, node.action_type.value)
                accumulator = accumulators[key]
                accumulator.candidate_count += 1
                if node.score is not None:
                    accumulator.scored_node_count += 1
                    accumulator.accumulated_score += node.score.total_score
                    if node.score.hard_constraint_pass and node.score.total_score >= _STRONG_SCORE_THRESHOLD:
                        accumulator.strong_score_count += 1
                if _was_admitted(node, state):
                    accumulator.admitted_count += 1
                elif node.lifecycle_status is NodeLifecycleStatus.REJECTED:
                    accumulator.rejected_count += 1
                elif (
                    node.lifecycle_status is NodeLifecycleStatus.FAILED
                    or (node.score is not None and not node.score.hard_constraint_pass)
                ):
                    accumulator.hard_fail_count += 1
                if node.node_id in stress_test_survivors:
                    accumulator.stress_test_survivor_count += 1
                if node.node_id in state.winner_ids:
                    accumulator.winner_count += 1
                if node.node_id in winner_contributors:
                    accumulator.winner_contribution_count += 1

        entries = [
            ProviderRoutingStatsEntry(
                provider_name=provider_name,
                action_name=action_name,
                run_count=accumulator.run_count,
                invocation_count=accumulator.invocation_count,
                provider_failure_count=accumulator.provider_failure_count,
                candidate_count=accumulator.candidate_count,
                scored_node_count=accumulator.scored_node_count,
                admitted_count=accumulator.admitted_count,
                rejected_count=accumulator.rejected_count,
                hard_fail_count=accumulator.hard_fail_count,
                strong_score_count=accumulator.strong_score_count,
                stress_test_survivor_count=accumulator.stress_test_survivor_count,
                winner_count=accumulator.winner_count,
                winner_contribution_count=accumulator.winner_contribution_count,
                critique_count=accumulator.critique_count,
                useful_critique_count=accumulator.useful_critique_count,
                learning_note_count=accumulator.learning_note_count,
                accumulated_score=round(accumulator.accumulated_score, 6),
                total_reward=round(accumulator.total_reward(), 6),
                last_run_id=normalized_run_id,
                last_updated_at=updated_at,
            )
            for (provider_name, action_name), accumulator in sorted(accumulators.items())
        ]
        return ProviderRoutingStats(entries=entries, updated_at=updated_at)

    def _all_keys(self, state: SearchState | None) -> set[tuple[str, str]]:
        keys = set(self._invocations)
        keys.update(self._provider_failures)
        keys.update(self._critiques)
        keys.update(self._learning_note_counts)
        if state is not None:
            for node in state.nodes.values():
                keys.add((node.provider_name, node.action_type.value))
        return keys

    def _key(
        self,
        action_name: str,
        provider_name: str | None,
    ) -> tuple[str, str]:
        return (
            _normalize_non_empty_string(
                provider_name or self._default_provider_name,
                "provider_name",
            ),
            _normalize_non_empty_string(action_name, "action_name"),
        )


def _node_snapshot_payload(node: Node) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "node_id": node.node_id,
        "action_type": node.action_type.value,
        "candidate": node.candidate.to_dict(),
        "novelty_score": node.novelty_score,
        "lifecycle_status": node.lifecycle_status.value,
    }
    if node.score is not None:
        payload["score"] = node.score.to_dict()
    if node.critique is not None:
        payload["critique"] = node.critique.to_dict()
    return payload


def _evaluation_metadata(assessment: object) -> dict[str, JSONValue]:
    from argus.eval import EvaluationAssessment

    if not isinstance(assessment, EvaluationAssessment):
        raise ArgusValidationError(
            "assessment must be an EvaluationAssessment instance."
        )
    return {
        "summary": assessment.summary,
        "strengths": list(assessment.strengths),
        "weaknesses": list(assessment.weaknesses),
        "open_questions": list(assessment.open_questions),
    }


_STRONG_SCORE_THRESHOLD = 6.0


def _is_useful_critique(critique: object) -> bool:
    from argus.models import Critique

    if not isinstance(critique, Critique):
        raise ArgusValidationError("critique must be a Critique instance.")
    return bool(
        critique.hidden_dependencies
        or critique.kill_shots
        or critique.sharp_edges
    )


def _was_admitted(node: Node, state: SearchState) -> bool:
    return node.node_id in state.archive_ids or node.lifecycle_status in {
        NodeLifecycleStatus.ADMITTED,
        NodeLifecycleStatus.ARCHIVED,
        NodeLifecycleStatus.WINNER,
    }


def _winner_contributor_ids(state: SearchState) -> set[str]:
    contributors: set[str] = set()
    pending = list(state.winner_ids)
    while pending:
        node_id = pending.pop()
        if node_id in contributors or node_id not in state.nodes:
            continue
        contributors.add(node_id)
        pending.extend(state.nodes[node_id].parent_ids)
    return contributors


def _stress_test_survivor_ids(
    state: SearchState,
    winner_contributors: set[str],
) -> set[str]:
    expanded_parent_ids = {
        parent_id
        for node in state.nodes.values()
        for parent_id in node.parent_ids
    }
    return {
        node.node_id
        for node in state.nodes.values()
        if node.critique is not None
        and (node.node_id in expanded_parent_ids or node.node_id in winner_contributors)
    }


def _is_rankable(node: Node) -> bool:
    return (
        node.score is not None
        and node.score.hard_constraint_pass
        and node.lifecycle_status
        not in {
            NodeLifecycleStatus.REJECTED,
            NodeLifecycleStatus.FAILED,
            NodeLifecycleStatus.PRUNED,
        }
    )


def _finalist_nodes(state: SearchState) -> list[Node]:
    candidates = [
        state.nodes[node_id]
        for node_id in state.archive_ids
        if node_id in state.nodes and _is_rankable(state.nodes[node_id])
    ]
    if candidates:
        return candidates
    fallback = [
        node
        for node in state.nodes.values()
        if node.score is not None and node.score.hard_constraint_pass
    ]
    return rank_nodes(fallback) if fallback else []


def _select_distinct_candidate(
    nodes: Sequence[Node],
    *,
    excluded_ids: set[str],
    key,
) -> Node | None:
    candidates = [node for node in nodes if node.node_id not in excluded_ids]
    if not candidates:
        return None
    return max(candidates, key=key)


def _select_rejected_nodes(state: SearchState, *, limit: int) -> list[Node]:
    rejected = [
        state.nodes[node_id]
        for node_id in state.pruned_ids
        if node_id in state.nodes and state.nodes[node_id].score is not None
    ]
    duplicates = [
        node
        for node in state.nodes.values()
        if node.lifecycle_status is NodeLifecycleStatus.REJECTED
    ]
    combined = rejected + [node for node in duplicates if node.node_id not in {item.node_id for item in rejected}]
    if not combined:
        alternatives = [
            node
            for node in state.nodes.values()
            if node.node_id not in state.winner_ids and node.score is not None
        ]
        combined = rank_nodes(alternatives)
    return sorted(
        combined,
        key=lambda node: (
            node.novelty_score,
            0.0 if node.score is None else node.score.total_score,
        ),
        reverse=True,
    )[:limit]


def _collect_unique_strings(values: Sequence[str], *, limit: int) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
        if len(results) >= limit:
            break
    return results


def _build_next_experiments(best: Node) -> list[str]:
    experiments: list[str] = []
    for unknown in best.candidate.unknowns[:2]:
        experiments.append(f"Validate the open question: {unknown}")
    for failure_mode in best.candidate.failure_modes[:1]:
        experiments.append(f"Pressure-test the failure mode: {failure_mode}")
    if best.critique is not None:
        for dependency in best.critique.hidden_dependencies[:1]:
            experiments.append(f"De-risk the hidden dependency: {dependency}")
    if not experiments:
        experiments.append("Prototype the best bet and measure whether the mechanism works in real operator workflow.")
    return _collect_unique_strings(experiments, limit=4)


def _render_summary_markdown(
    *,
    problem_spec: ProblemSpec,
    best: Node,
    conservative: Node,
    high_upside: Node,
    rejected: Sequence[Node],
    learning_notes: Sequence[LearningNote],
    next_experiments: Sequence[str],
    assumptions: Sequence[str],
    failure_modes: Sequence[str],
    reversal_conditions: Sequence[str],
) -> str:
    lines = [
        "# Argus Recommendation",
        "",
        "## Refined Problem Frame",
        problem_spec.request,
        "",
    ]
    if problem_spec.constraints:
        lines.extend(["Constraints:"] + [f"- {item}" for item in problem_spec.constraints] + [""])
    if problem_spec.success_criteria:
        lines.extend(
            ["Success criteria:"]
            + [f"- {item}" for item in problem_spec.success_criteria]
            + [""]
        )

    lines.extend(
        [
            "## Best Bet",
            f"{best.candidate.thesis} (`{best.node_id}`)",
            f"- Mechanism: {best.candidate.mechanism}",
            "",
            "## Conservative Option",
            f"{conservative.candidate.thesis} (`{conservative.node_id}`)",
            f"- Mechanism: {conservative.candidate.mechanism}",
            "",
            "## High-Upside Option",
            f"{high_upside.candidate.thesis} (`{high_upside.node_id}`)",
            f"- Mechanism: {high_upside.candidate.mechanism}",
            "",
            "## Rejected But Insightful",
        ]
    )
    if rejected:
        for node in rejected:
            lines.append(f"- `{node.node_id}`: {node.candidate.thesis}")
    else:
        lines.append("- None.")
    lines.append("")

    lines.append("## Assumptions")
    for assumption in assumptions:
        lines.append(f"- {assumption}")
    if not assumptions:
        lines.append("- None recorded.")
    lines.append("")

    lines.append("## Failure Modes")
    for failure_mode in failure_modes:
        lines.append(f"- {failure_mode}")
    if not failure_modes:
        lines.append("- None recorded.")
    lines.append("")

    lines.append("## Next Experiments")
    for experiment in next_experiments:
        lines.append(f"- {experiment}")
    lines.append("")

    lines.append("## Reasons This Could Be Wrong")
    for condition in reversal_conditions:
        lines.append(f"- {condition}")
    if not reversal_conditions:
        lines.append("- The current evidence may overrate a candidate that has not faced real-world constraints yet.")
    lines.append("")

    if learning_notes:
        lines.append("## Learning Notes")
        for note in learning_notes:
            lines.append(f"- {note.note_type.value}: {note.text}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _normalize_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
