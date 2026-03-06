from __future__ import annotations

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
        current_action = ActionType.FRAME_PROBLEM.value
        try:
            frame = self._frame_problem(initial_problem_spec, budget)
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
                self._generate_seed_nodes(session)
                self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            session.refresh_frontier(limit=self._policy.frontier_limit)

            current_action = ActionType.STRESS_TEST.value
            self._stress_test_frontier(session, budget)
            self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            session.refresh_frontier(limit=self._policy.frontier_limit)

            current_action = ActionType.DEEPEN.value
            self._deepen_frontier(session, budget)
            self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.RANK.value
            session.record_internal_step()
            session.refresh_frontier(limit=self._policy.frontier_limit)

            current_action = ActionType.MUTATE.value
            self._mutate_survivors(session, budget)

            current_action = ActionType.COMBINE.value
            self._combine_survivors(session, budget)
            self._persist_running_snapshot(manifest.run_id, session)

            current_action = ActionType.COMPRESS_LEARNING.value
            self._compress_learning(session, budget)

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
            summary_markdown = recommendation.summary_markdown
            refreshed_manifest = self._state_store.save_snapshot(
                manifest.run_id,
                state=final_state,
                final_recommendation=recommendation,
                summary_markdown=summary_markdown,
                status=RunStatus.COMPLETED,
                metadata_patch={
                    "best_bet_node_id": recommendation.best_bet_node_id,
                    "winner_count": len(final_state.winner_ids),
                },
            )
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
            if session is None:
                self._state_store.update_manifest_status(
                    manifest.run_id,
                    status=RunStatus.FAILED,
                    error=str(exc),
                    metadata_patch=failure_metadata,
                )
            else:
                self._state_store.save_snapshot(
                    manifest.run_id,
                    state=session.snapshot(),
                    status=RunStatus.FAILED,
                    error=str(exc),
                    metadata_patch=failure_metadata,
                )
            raise

    def _frame_problem(self, problem_spec: ProblemSpec, budget: int) -> ProblemFrame:
        response = self._provider.run_action(
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

    def _generate_seed_nodes(self, session: "_MutableSession") -> None:
        response = self._provider.run_action(
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

    def _stress_test_frontier(self, session: "_MutableSession", budget: int) -> None:
        for node in self._top_ranked_nodes(session, limit=self._policy.stress_test_limit):
            if session.budget_spent >= budget:
                break
            response = self._provider.run_action(
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
            updated = replace(
                node,
                critique=critique,
                metadata={
                    **node.metadata,
                    "stress_test": critique.to_dict(),
                },
            )
            session.replace_node(updated)

    def _deepen_frontier(self, session: "_MutableSession", budget: int) -> None:
        for node in self._top_ranked_nodes(session, limit=self._policy.deepen_limit):
            if session.budget_spent >= budget:
                break
            response = self._provider.run_action(
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

    def _mutate_survivors(self, session: "_MutableSession", budget: int) -> None:
        mutations = 0
        for node in self._top_ranked_nodes(session, limit=self._policy.mutate_limit):
            if mutations >= self._policy.mutate_limit or session.budget_spent >= budget:
                break
            response = self._provider.run_action(
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

    def _combine_survivors(self, session: "_MutableSession", budget: int) -> None:
        if self._policy.combine_limit <= 0 or session.budget_spent >= budget:
            return
        ranked = self._top_ranked_nodes(session, limit=2)
        if len(ranked) < 2:
            return
        response = self._provider.run_action(
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

    def _compress_learning(self, session: "_MutableSession", budget: int) -> None:
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

        response = self._provider.run_action(
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
        session.set_learning_notes(compression.notes[: self._policy.max_learning_notes])
        session.refresh_frontier(limit=self._policy.frontier_limit)

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
