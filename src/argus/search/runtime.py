from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TypeVar

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
    FinalRecommendation,
    JSONValue,
    LearningMemory,
    LearningNote,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    ReusableLearningNote,
    SearchIsland,
    SearchState,
)
from argus.providers import Provider, StructuredOutputSchema
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
class SearchIslandPolicy:
    island_id: str
    label: str
    description: str
    selection_mode: str
    generation_focus: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "island_id", _normalize_non_empty_string(self.island_id, "island_id"))
        object.__setattr__(self, "label", _normalize_non_empty_string(self.label, "label"))
        object.__setattr__(self, "description", _normalize_non_empty_string(self.description, "description"))
        object.__setattr__(
            self,
            "selection_mode",
            _normalize_non_empty_string(self.selection_mode, "selection_mode"),
        )
        object.__setattr__(
            self,
            "generation_focus",
            _normalize_non_empty_string(self.generation_focus, "generation_focus"),
        )
        if self.selection_mode not in {"balanced", "conservative", "upside"}:
            raise ArgusValidationError(
                "selection_mode must be one of balanced, conservative, or upside."
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "island_id": self.island_id,
            "label": self.label,
            "description": self.description,
            "selection_mode": self.selection_mode,
            "generation_focus": self.generation_focus,
        }

    def to_search_island(
        self,
        *,
        archive_ids: Sequence[str],
        frontier_ids: Sequence[str],
        pruned_ids: Sequence[str],
    ) -> SearchIsland:
        return SearchIsland(
            island_id=self.island_id,
            label=self.label,
            description=self.description,
            archive_ids=list(archive_ids),
            frontier_ids=list(frontier_ids),
            pruned_ids=list(pruned_ids),
        )

    def to_prompt_dict(self) -> dict[str, JSONValue]:
        return {
            "island_id": self.island_id,
            "label": self.label,
            "description": self.description,
            "selection_mode": self.selection_mode,
            "generation_focus": self.generation_focus,
        }


def balanced_island_policy() -> SearchIslandPolicy:
    return SearchIslandPolicy(
        island_id="balanced",
        label="Balanced",
        description=(
            "Explore candidates that balance usefulness, specificity, plausibility, "
            "tractability, and upside without overfitting to any single dimension."
        ),
        selection_mode="balanced",
        generation_focus=(
            "Favor well-rounded mechanisms that could win on substance, not just on safety "
            "or upside alone."
        ),
    )


def conservative_island_policy() -> SearchIslandPolicy:
    return SearchIslandPolicy(
        island_id="conservative",
        label="Conservative",
        description=(
            "Explore safer, implementation-ready directions that still meaningfully solve "
            "the problem under the stated constraints."
        ),
        selection_mode="conservative",
        generation_focus=(
            "Favor operational clarity, tractability, robust rollout paths, and low-regret "
            "adoption wedges."
        ),
    )


def upside_island_policy() -> SearchIslandPolicy:
    return SearchIslandPolicy(
        island_id="upside",
        label="High Upside",
        description=(
            "Explore differentiated bets with larger ceilings while still demanding a "
            "defensible mechanism and explicit tradeoffs."
        ),
        selection_mode="upside",
        generation_focus=(
            "Favor high-leverage or network-style opportunities, but keep the mechanism "
            "concrete enough to evaluate and stress-test."
        ),
    )


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
    reusable_learning_limit: int = 4
    provider_max_concurrency: int = 4
    island_policies: tuple[SearchIslandPolicy, ...] = field(
        default_factory=lambda: (balanced_island_policy(),)
    )

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
            "reusable_learning_limit",
            "provider_max_concurrency",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value <= 0:
                raise ArgusValidationError(f"{field_name} must be a positive integer.")
        if not isinstance(self.island_policies, tuple) or not self.island_policies:
            raise ArgusValidationError("island_policies must be a non-empty tuple.")
        seen_island_ids: set[str] = set()
        for index, island in enumerate(self.island_policies):
            if not isinstance(island, SearchIslandPolicy):
                raise ArgusValidationError(
                    f"island_policies[{index}] must be a SearchIslandPolicy instance."
                )
            if island.island_id in seen_island_ids:
                raise ArgusValidationError(
                    f"island_policies contains duplicate island_id values: {island.island_id}."
                )
            seen_island_ids.add(island.island_id)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "seed_target": self.seed_target,
            "stress_test_limit": self.stress_test_limit,
            "deepen_limit": self.deepen_limit,
            "mutate_limit": self.mutate_limit,
            "combine_limit": self.combine_limit,
            "frontier_limit": self.frontier_limit,
            "rejected_limit": self.rejected_limit,
            "max_learning_notes": self.max_learning_notes,
            "reusable_learning_limit": self.reusable_learning_limit,
            "provider_max_concurrency": self.provider_max_concurrency,
            "islands": [island.to_dict() for island in self.island_policies],
        }


@dataclass(frozen=True, slots=True)
class SearchRunResult:
    run_path: Path
    manifest: RunManifest
    state: SearchState
    final_recommendation: FinalRecommendation
    summary_markdown: str


@dataclass(frozen=True, slots=True)
class _PairwiseDecisionRecord:
    selection_label: str
    left_node_id: str
    right_node_id: str
    winner_node_id: str
    assessment: PairwiseRankingAssessment


@dataclass(frozen=True, slots=True)
class _CandidateAdmissionRequest:
    candidate: Candidate
    parent_ids: tuple[str, ...]
    batch_summary: str


@dataclass(frozen=True, slots=True)
class _PreparedCandidateAdmission:
    novelty: NoveltyAssessment
    assessment: EvaluationAssessment


@dataclass(frozen=True, slots=True)
class _IslandNodeSelection:
    island_id: str
    node: Node


@dataclass(frozen=True, slots=True)
class _ProviderActionRequest:
    action_name: ActionType
    problem_spec: ProblemSpec
    input_payload: dict[str, JSONValue]
    output_schema: StructuredOutputSchema[object]


T = TypeVar("T")
R = TypeVar("R")


class SearchRuntime:
    def __init__(
        self,
        *,
        provider: Provider,
        state_store: FileSystemStateStore,
        policy: SearchPolicy | None = None,
        reuse_learning_memory: bool = True,
    ) -> None:
        self._provider = provider
        self._state_store = state_store
        self._policy = policy or SearchPolicy()
        if not isinstance(reuse_learning_memory, bool):
            raise ArgusValidationError("reuse_learning_memory must be a boolean.")
        self._reuse_learning_memory = reuse_learning_memory
        self._evaluator = AgenticEvaluator(provider=provider)
        self._novelty_filter = AgenticNoveltyFilter(provider=provider)

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def policy(self) -> SearchPolicy:
        return self._policy

    def _select_reusable_learning_context(
        self,
        problem_spec: ProblemSpec,
    ) -> LearningMemory:
        if not self._reuse_learning_memory:
            return LearningMemory.empty()
        return self._state_store.load_learning_memory().select_for_problem(
            problem_spec,
            limit=self._policy.reusable_learning_limit,
        )

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
        reusable_learning_context = self._select_reusable_learning_context(initial_problem_spec)
        if reusable_learning_context.entries:
            self._state_store.save_reusable_learning_context(
                manifest.run_id,
                reusable_learning_context,
            )

        session: _MutableSession | None = None
        routing_tracker = _RoutingTracker(default_provider_name=self._provider.name)
        current_action = ActionType.FRAME_PROBLEM.value
        try:
            frame = self._frame_problem(
                initial_problem_spec,
                budget,
                routing_tracker,
                reusable_learning_context.entries,
            )
            root_node = self._build_framing_node(
                frame,
                reusable_learning_context.entries,
            )
            session = _MutableSession(
                problem_spec=frame.problem_spec,
                root_node=root_node,
                budget_spent=1,
                step_count=1,
                island_policies=self._policy.island_policies,
            )
            session.set_learning_notes([])
            session.set_reusable_learning_notes(reusable_learning_context.entries)
            session.refresh_frontier(limit=self._policy.frontier_limit)
            self._persist_running_snapshot(manifest.run_id, session, frame_summary=frame.framing_notes)

            if session.budget_spent < budget:
                current_action = ActionType.GENERATE_SEED.value
                self._generate_seed_nodes(session, budget, routing_tracker)
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
            recommendation = self._compile_final_recommendation(
                session.snapshot(),
                routing_tracker,
                session.reusable_learning_notes,
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
                final_recommendation=recommendation,
                summary_markdown=summary_markdown,
                routing_summary=routing_summary,
                status=RunStatus.COMPLETED,
                metadata_patch={
                    "best_bet_node_id": recommendation.best_bet_node_id,
                    "winner_count": len(final_state.winner_ids),
                },
            )
            current_action = "persist_learning_memory"
            if self._reuse_learning_memory and final_state.learning_notes:
                self._state_store.merge_learning_memory(
                    run_id=manifest.run_id,
                    problem_spec=final_state.problem_spec,
                    notes=final_state.learning_notes,
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
        reusable_learning_notes: Sequence[ReusableLearningNote],
    ) -> ProblemFrame:
        input_payload: dict[str, JSONValue] = {
            "request": problem_spec.request,
            "budget": budget,
            "search_policy": self._policy.to_dict(),
            "framing_requirements": [
                "Normalize explicit constraints.",
                "Normalize success criteria.",
                "Produce a framing candidate that captures the most decision-relevant angle.",
            ],
        }
        if reusable_learning_notes:
            input_payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in reusable_learning_notes
            ]
        response = self._run_provider_action(
            routing_tracker,
            action_name=ActionType.FRAME_PROBLEM,
            problem_spec=problem_spec,
            input_payload=input_payload,
            output_schema=problem_frame_schema(),
        )
        return response.payload

    def _build_framing_node(
        self,
        frame: ProblemFrame,
        reusable_learning_notes: Sequence[ReusableLearningNote],
    ) -> Node:
        assessment = self._evaluator.evaluate(
            frame.problem_spec,
            frame.framing_candidate,
            novelty_score=1.0,
            reusable_learning_notes=reusable_learning_notes,
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
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        remaining_budget = max(budget - session.budget_spent, 0)
        if remaining_budget <= 0:
            return

        target_count_by_island = _allocate_targets(
            self._policy.seed_target,
            len(session.island_ids),
        )
        island_requests: list[tuple[str, _ProviderActionRequest]] = []
        for island_id, target_count in zip(session.island_ids[:remaining_budget], target_count_by_island):
            if target_count <= 0:
                continue
            input_payload: dict[str, JSONValue] = {
                "target_count": target_count,
                "island": session.island_prompt(island_id),
                "framing_candidate": session.root_node.candidate.to_dict(),
                "learning_notes": [note.to_dict() for note in session.learning_notes],
                "generation_policy": {
                    "diversity_requirement": (
                        "Return materially distinct strategic directions, not paraphrases."
                    ),
                    "quality_requirement": (
                        "Prefer executable mechanisms with explicit assumptions and failure modes."
                    ),
                    "island_focus": session.island_policy(island_id).generation_focus,
                },
            }
            if session.reusable_learning_notes:
                input_payload["reusable_learning_notes"] = [
                    note.to_prompt_dict() for note in session.reusable_learning_notes
                ]
            island_requests.append(
                (
                    island_id,
                    _ProviderActionRequest(
                        action_name=ActionType.GENERATE_SEED,
                        problem_spec=session.problem_spec,
                        input_payload=input_payload,
                        output_schema=candidate_batch_schema(),
                    ),
                )
            )

        responses = self._dispatch_provider_requests(
            routing_tracker,
            [request for _, request in island_requests],
        )
        for (island_id, _), response in zip(island_requests, responses):
            session.consume_budget()
            batch = response.payload
            self._admit_candidate_batch(
                session,
                island_id=island_id,
                action_type=ActionType.GENERATE_SEED,
                requests=[
                    _CandidateAdmissionRequest(
                        candidate=candidate,
                        parent_ids=(session.root_id,),
                        batch_summary=batch.batch_summary,
                    )
                    for candidate in batch.candidates
                ],
            )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _stress_test_frontier(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        remaining_budget = max(budget - session.budget_spent, 0)
        if remaining_budget <= 0:
            return

        selected_nodes = self._select_stage_nodes(
            session,
            limit=min(self._policy.stress_test_limit, remaining_budget),
            stage_name=ActionType.STRESS_TEST,
        )
        requests: list[_ProviderActionRequest] = []
        for selection in selected_nodes:
            node = selection.node
            input_payload: dict[str, JSONValue] = {
                "node_id": node.node_id,
                "island": session.island_prompt(selection.island_id),
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
            }
            if session.reusable_learning_notes:
                input_payload["reusable_learning_notes"] = [
                    note.to_prompt_dict() for note in session.reusable_learning_notes
                ]
            requests.append(
                _ProviderActionRequest(
                    action_name=ActionType.STRESS_TEST,
                    problem_spec=session.problem_spec,
                    input_payload=input_payload,
                    output_schema=critique_schema(),
                )
            )

        responses = self._dispatch_provider_requests(routing_tracker, requests)
        for selection, response in zip(selected_nodes, responses):
            session.consume_budget()
            node = selection.node
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
        remaining_budget = max(budget - session.budget_spent, 0)
        if remaining_budget <= 0:
            return

        selected_nodes = self._select_stage_nodes(
            session,
            limit=min(self._policy.deepen_limit, remaining_budget),
            stage_name=ActionType.DEEPEN,
        )
        requests: list[_ProviderActionRequest] = []
        for selection in selected_nodes:
            node = selection.node
            input_payload: dict[str, JSONValue] = {
                "node_id": node.node_id,
                "island": session.island_prompt(selection.island_id),
                "candidate": node.candidate.to_dict(),
                "score": None if node.score is None else node.score.to_dict(),
                "critique": None if node.critique is None else node.critique.to_dict(),
                "learning_notes": [note.to_dict() for note in session.learning_notes],
                "deepen_policy": {
                    "goal": (
                        "Increase specificity and execution readiness without collapsing distinctiveness."
                    ),
                },
            }
            if session.reusable_learning_notes:
                input_payload["reusable_learning_notes"] = [
                    note.to_prompt_dict() for note in session.reusable_learning_notes
                ]
            requests.append(
                _ProviderActionRequest(
                    action_name=ActionType.DEEPEN,
                    problem_spec=session.problem_spec,
                    input_payload=input_payload,
                    output_schema=candidate_schema(),
                )
            )

        responses = self._dispatch_provider_requests(routing_tracker, requests)
        admission_requests: list[_CandidateAdmissionRequest] = []
        for selection, response in zip(selected_nodes, responses):
            session.consume_budget()
            admission_requests.append(
                _CandidateAdmissionRequest(
                    candidate=response.payload,
                    parent_ids=(selection.node.node_id,),
                    batch_summary="Deepened a high-scoring survivor.",
                )
            )
        for selection, admission_request in zip(selected_nodes, admission_requests):
            self._admit_candidate_batch(
                session,
                island_id=selection.island_id,
                action_type=ActionType.DEEPEN,
                requests=[admission_request],
            )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _mutate_survivors(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        remaining_budget = max(budget - session.budget_spent, 0)
        if remaining_budget <= 0:
            return

        selected_nodes = self._select_stage_nodes(
            session,
            limit=min(self._policy.mutate_limit, remaining_budget),
            stage_name=ActionType.MUTATE,
        )
        requests: list[_ProviderActionRequest] = []
        for selection in selected_nodes:
            node = selection.node
            input_payload: dict[str, JSONValue] = {
                "node_id": node.node_id,
                "island": session.island_prompt(selection.island_id),
                "candidate": node.candidate.to_dict(),
                "score": None if node.score is None else node.score.to_dict(),
                "critique": None if node.critique is None else node.critique.to_dict(),
                "mutation_policy": {
                    "goal": "Address the sharpest weakness while preserving the core mechanism.",
                },
            }
            if session.reusable_learning_notes:
                input_payload["reusable_learning_notes"] = [
                    note.to_prompt_dict() for note in session.reusable_learning_notes
                ]
            requests.append(
                _ProviderActionRequest(
                    action_name=ActionType.MUTATE,
                    problem_spec=session.problem_spec,
                    input_payload=input_payload,
                    output_schema=candidate_batch_schema(),
                )
            )

        responses = self._dispatch_provider_requests(routing_tracker, requests)
        for selection, response in zip(selected_nodes, responses):
            session.consume_budget()
            self._admit_candidate_batch(
                session,
                island_id=selection.island_id,
                action_type=ActionType.MUTATE,
                requests=[
                    _CandidateAdmissionRequest(
                        candidate=candidate,
                        parent_ids=(selection.node.node_id,),
                        batch_summary=response.payload.batch_summary,
                    )
                    for candidate in response.payload.candidates
                ],
            )
        session.refresh_frontier(limit=self._policy.frontier_limit)

    def _combine_survivors(
        self,
        session: "_MutableSession",
        budget: int,
        routing_tracker: "_RoutingTracker",
    ) -> None:
        remaining_budget = max(budget - session.budget_spent, 0)
        if self._policy.combine_limit <= 0 or remaining_budget <= 0:
            return

        selected_pairs = self._select_combine_pairs(
            session,
            limit=min(self._policy.combine_limit, remaining_budget),
        )
        if not selected_pairs:
            return
        requests: list[_ProviderActionRequest] = []
        for island_id, primary, secondary in selected_pairs:
            input_payload: dict[str, JSONValue] = {
                "island": session.island_prompt(island_id),
                "primary_node_id": primary.node_id,
                "secondary_node_id": secondary.node_id,
                "primary_candidate": primary.candidate.to_dict(),
                "secondary_candidate": secondary.candidate.to_dict(),
                "combine_policy": {
                    "goal": (
                        "Fuse compatible strengths only if the combined direction remains coherent and distinct."
                    ),
                },
            }
            if session.reusable_learning_notes:
                input_payload["reusable_learning_notes"] = [
                    note.to_prompt_dict() for note in session.reusable_learning_notes
                ]
            requests.append(
                _ProviderActionRequest(
                    action_name=ActionType.COMBINE,
                    problem_spec=session.problem_spec,
                    input_payload=input_payload,
                    output_schema=candidate_batch_schema(),
                )
            )

        responses = self._dispatch_provider_requests(routing_tracker, requests)
        for (island_id, primary, secondary), response in zip(selected_pairs, responses):
            session.consume_budget()
            self._admit_candidate_batch(
                session,
                island_id=island_id,
                action_type=ActionType.COMBINE,
                requests=[
                    _CandidateAdmissionRequest(
                        candidate=candidate,
                        parent_ids=(primary.node_id, secondary.node_id),
                        batch_summary=response.payload.batch_summary,
                    )
                    for candidate in response.payload.candidates
                ],
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

        input_payload: dict[str, JSONValue] = {
            "archived_nodes": archived_nodes,
            "pruned_nodes": pruned_nodes,
            "islands": [
                {
                    **session.island_prompt(island_id),
                    "archive_count": len(session.islands[island_id].archive_ids),
                    "frontier_count": len(session.islands[island_id].frontier_ids),
                    "pruned_count": len(session.islands[island_id].pruned_ids),
                }
                for island_id in session.island_ids
            ],
            "max_notes": self._policy.max_learning_notes,
            "compression_policy": {
                "goal": "Extract reusable patterns, failure modes, and constraints from the current search state.",
            },
        }
        if session.reusable_learning_notes:
            input_payload["reusable_learning_notes"] = [
                note.to_prompt_dict() for note in session.reusable_learning_notes
            ]
        response = self._run_provider_action(
            routing_tracker,
            action_name=ActionType.COMPRESS_LEARNING,
            problem_spec=session.problem_spec,
            input_payload=input_payload,
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

    def _dispatch_provider_requests(
        self,
        routing_tracker: "_RoutingTracker",
        requests: Sequence[_ProviderActionRequest],
    ) -> list[object]:
        return self._run_bounded_tasks(
            requests,
            lambda request: self._run_provider_action(
                routing_tracker,
                action_name=request.action_name,
                problem_spec=request.problem_spec,
                input_payload=request.input_payload,
                output_schema=request.output_schema,
            ),
        )

    def _run_bounded_tasks(
        self,
        items: Sequence[T],
        worker: Callable[[T], R],
    ) -> list[R]:
        if not items:
            return []
        if len(items) == 1 or self._policy.provider_max_concurrency == 1:
            return [worker(item) for item in items]

        max_workers = min(self._policy.provider_max_concurrency, len(items))
        results: list[R | None] = [None] * len(items)
        failures: dict[int, Exception] = {}
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"argus-{self._provider.name}",
        ) as executor:
            future_map = {
                executor.submit(worker, item): index
                for index, item in enumerate(items)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    failures[index] = exc

        if failures:
            raise failures[min(failures)]
        return [result for result in results if result is not None]

    def _admit_candidate(
        self,
        session: "_MutableSession",
        *,
        island_id: str | None,
        action_type: ActionType,
        candidate: Candidate,
        parent_ids: Sequence[str],
        batch_summary: str,
    ) -> Node:
        prepared = self._prepare_candidate_admission(
            problem_spec=session.problem_spec,
            candidate=candidate,
            archive_nodes=[session.nodes[node_id] for node_id in session.archive_ids],
            reusable_learning_notes=session.reusable_learning_notes,
        )
        return self._commit_candidate_admission(
            session,
            island_id=island_id,
            action_type=action_type,
            candidate=candidate,
            parent_ids=parent_ids,
            batch_summary=batch_summary,
            novelty=prepared.novelty,
            assessment=prepared.assessment,
        )

    def _admit_candidate_batch(
        self,
        session: "_MutableSession",
        *,
        island_id: str | None,
        action_type: ActionType,
        requests: Sequence[_CandidateAdmissionRequest],
    ) -> list[Node]:
        if not requests:
            return []

        archive_snapshot = [session.nodes[node_id] for node_id in session.archive_ids]
        prepared = self._run_bounded_tasks(
            requests,
            lambda request: self._prepare_candidate_admission(
                problem_spec=session.problem_spec,
                candidate=request.candidate,
                archive_nodes=archive_snapshot,
                reusable_learning_notes=session.reusable_learning_notes,
            ),
        )
        admitted_batch_nodes: list[Node] = []
        committed: list[Node] = []
        for request, prepared_candidate in zip(requests, prepared):
            novelty = prepared_candidate.novelty
            if novelty.is_novel and admitted_batch_nodes:
                # Concurrent archive checks use a fixed snapshot; final batch admission
                # stays serial so same-batch near-duplicates cannot both land.
                novelty = _merge_novelty_assessments(
                    archive_novelty=novelty,
                    intra_batch_novelty=self._novelty_filter.assess(
                        problem_spec=session.problem_spec,
                        candidate=request.candidate,
                        archive_nodes=admitted_batch_nodes,
                    ),
                )
            node = self._commit_candidate_admission(
                session,
                island_id=island_id,
                action_type=action_type,
                candidate=request.candidate,
                parent_ids=request.parent_ids,
                batch_summary=request.batch_summary,
                novelty=novelty,
                assessment=prepared_candidate.assessment,
            )
            committed.append(node)
            if node.node_id in session.archive_ids:
                admitted_batch_nodes.append(node)
        return committed

    def _prepare_candidate_admission(
        self,
        *,
        problem_spec: ProblemSpec,
        candidate: Candidate,
        archive_nodes: Sequence[Node],
        reusable_learning_notes: Sequence[ReusableLearningNote],
    ) -> _PreparedCandidateAdmission:
        novelty = self._novelty_filter.assess(
            problem_spec=problem_spec,
            candidate=candidate,
            archive_nodes=archive_nodes,
        )
        assessment = self._evaluator.evaluate(
            problem_spec,
            candidate,
            novelty_score=novelty.novelty_score,
            reusable_learning_notes=reusable_learning_notes,
        )
        return _PreparedCandidateAdmission(
            novelty=novelty,
            assessment=assessment,
        )

    def _commit_candidate_admission(
        self,
        session: "_MutableSession",
        *,
        island_id: str | None,
        action_type: ActionType,
        candidate: Candidate,
        parent_ids: Sequence[str],
        batch_summary: str,
        novelty: NoveltyAssessment,
        assessment: EvaluationAssessment,
    ) -> Node:
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
            island_id=island_id,
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
            session.mark_pruned(node.node_id, island_id=island_id)
            return node
        session.archive(node.node_id, island_id=island_id)
        return node

    def _select_stage_nodes(
        self,
        session: "_MutableSession",
        *,
        limit: int,
        stage_name: ActionType,
    ) -> list[_IslandNodeSelection]:
        if limit <= 0:
            return []

        phase_one: list[_IslandNodeSelection] = []
        leftovers: list[_IslandNodeSelection] = []
        for island_id in session.island_ids:
            ranked = session.rank_island_nodes(island_id)
            if not ranked:
                continue
            phase_one.append(_IslandNodeSelection(island_id=island_id, node=ranked[0]))
            leftovers.extend(
                _IslandNodeSelection(island_id=island_id, node=node)
                for node in ranked[1:]
            )

        selected = sorted(
            phase_one,
            key=lambda item: (
                _stage_priority_key(
                    item.node,
                    session.island_policy(item.island_id),
                ),
                -session.island_order(item.island_id),
            ),
            reverse=True,
        )[:limit]
        if len(selected) >= limit:
            return selected

        selected_ids = {(item.island_id, item.node.node_id) for item in selected}
        remaining = [
            item
            for item in leftovers
            if (item.island_id, item.node.node_id) not in selected_ids
        ]
        selected.extend(
            sorted(
                remaining,
                key=lambda item: (
                    _stage_priority_key(
                        item.node,
                        session.island_policy(item.island_id),
                    ),
                    -session.island_order(item.island_id),
                ),
                reverse=True,
            )[: limit - len(selected)]
        )
        return selected

    def _select_combine_pairs(
        self,
        session: "_MutableSession",
        *,
        limit: int,
    ) -> list[tuple[str, Node, Node]]:
        if limit <= 0:
            return []

        eligible_pairs: list[tuple[str, Node, Node]] = []
        for island_id in session.island_ids:
            ranked = [
                node
                for node in session.rank_island_nodes(island_id)
                if node.node_id != session.root_id
            ]
            if len(ranked) < 2:
                continue
            eligible_pairs.append((island_id, ranked[0], ranked[1]))
        return sorted(
            eligible_pairs,
            key=lambda item: (
                _stage_priority_key(item[1], session.island_policy(item[0])),
                -session.island_order(item[0]),
            ),
            reverse=True,
        )[:limit]

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
            "island_count": len(session.island_ids),
        }
        if frame_summary is not None:
            metadata_patch["frame_summary"] = list(frame_summary)
        self._state_store.save_snapshot(
            run_id,
            state=session.snapshot(),
            status=RunStatus.RUNNING,
            metadata_patch=metadata_patch,
        )

    def _compile_final_recommendation(
        self,
        state: SearchState,
        routing_tracker: "_RoutingTracker",
        reusable_learning_notes: Sequence[ReusableLearningNote],
    ) -> FinalRecommendation:
        candidates = _finalist_nodes(state)
        if not candidates:
            raise ArgusValidationError("Cannot compile a final recommendation without any viable nodes.")

        best, best_decisions = self._select_pairwise_candidate(
            state.problem_spec,
            candidates,
            selection_label="Best bet",
            objective_name="best_overall",
            objective_description=(
                "Choose the strongest overall recommendation. Balance usefulness, "
                "specificity, plausibility, implementation tractability, upside, "
                "and adversarial robustness against the refined problem frame."
            ),
            routing_tracker=routing_tracker,
            reusable_learning_notes=reusable_learning_notes,
        )
        if best is None:
            raise ArgusValidationError("Pairwise best-bet selection returned no candidate.")

        conservative_candidates = [
            node
            for node in candidates
            if node.node_id != best.node_id
        ]
        conservative, conservative_decisions = self._select_pairwise_candidate(
            state.problem_spec,
            conservative_candidates,
            selection_label="Conservative option",
            objective_name="conservative_option",
            objective_description=(
                "Choose the safer, more implementation-ready option that still "
                "meaningfully solves the problem. Prefer operational clarity, "
                "tractability, plausibility, and robustness over raw upside."
            ),
            routing_tracker=routing_tracker,
            reusable_learning_notes=reusable_learning_notes,
            pre_rank_key=lambda node: (
                node.score.implementation_tractability,
                node.score.plausibility,
                node.score.adversarial_robustness,
                node.score.confidence_estimate,
                node.score.total_score,
            ),
        )
        if conservative is None:
            conservative = best

        high_upside_candidates = [
            node
            for node in candidates
            if node.node_id not in {best.node_id, conservative.node_id}
        ]
        high_upside, high_upside_decisions = self._select_pairwise_candidate(
            state.problem_spec,
            high_upside_candidates,
            selection_label="High-upside option",
            objective_name="high_upside_option",
            objective_description=(
                "Choose the highest-upside option that still has a defensible mechanism. "
                "Reward justified upside and distinctiveness, but do not ignore "
                "implementation risk or realism."
            ),
            routing_tracker=routing_tracker,
            reusable_learning_notes=reusable_learning_notes,
            pre_rank_key=lambda node: (
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
        selection_checks = _pairwise_selection_notes(
            [
                *best_decisions,
                *conservative_decisions,
                *high_upside_decisions,
            ]
        )
        summary_markdown = _render_summary_markdown(
            problem_spec=state.problem_spec,
            islands=state.islands,
            best=best,
            conservative=conservative,
            high_upside=high_upside,
            rejected=rejected,
            learning_notes=state.learning_notes,
            next_experiments=next_experiments,
            assumptions=assumptions,
            failure_modes=failure_modes,
            reversal_conditions=reversal_conditions,
            selection_checks=selection_checks,
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

    def _select_pairwise_candidate(
        self,
        problem_spec: ProblemSpec,
        nodes: Sequence[Node],
        *,
        selection_label: str,
        objective_name: str,
        objective_description: str,
        routing_tracker: "_RoutingTracker",
        reusable_learning_notes: Sequence[ReusableLearningNote],
        pre_rank_key=None,
    ) -> tuple[Node | None, list[_PairwiseDecisionRecord]]:
        candidates = list(nodes)
        if not candidates:
            return None, []
        ordered = (
            rank_nodes(candidates)
            if pre_rank_key is None
            else sorted(candidates, key=pre_rank_key, reverse=True)
        )
        if len(ordered) == 1:
            return ordered[0], []

        left = ordered[0]
        right = ordered[1]
        assessment = self._compare_nodes_pairwise(
            problem_spec,
            left,
            right,
            objective_name=objective_name,
            objective_description=objective_description,
            routing_tracker=routing_tracker,
            reusable_learning_notes=reusable_learning_notes,
        )
        winner = left if assessment.winner == "left" else right
        return winner, [
            _PairwiseDecisionRecord(
                selection_label=selection_label,
                left_node_id=left.node_id,
                right_node_id=right.node_id,
                winner_node_id=winner.node_id,
                assessment=assessment,
            )
        ]

    def _compare_nodes_pairwise(
        self,
        problem_spec: ProblemSpec,
        left: Node,
        right: Node,
        *,
        objective_name: str,
        objective_description: str,
        routing_tracker: "_RoutingTracker",
        reusable_learning_notes: Sequence[ReusableLearningNote],
    ) -> PairwiseRankingAssessment:
        routing_tracker.record_invocation(
            action_name=ActionType.RANK.value,
            provider_name=self._provider.name,
        )
        try:
            return self._evaluator.compare_nodes(
                problem_spec,
                left,
                right,
                objective=objective_name,
                objective_description=objective_description,
                reusable_learning_notes=reusable_learning_notes,
            )
        except Exception:
            routing_tracker.record_provider_failure(
                action_name=ActionType.RANK.value,
                provider_name=self._provider.name,
            )
            raise


@dataclass(slots=True)
class _MutableIslandState:
    policy: SearchIslandPolicy
    archive_ids: list[str]
    frontier_ids: list[str]
    pruned_ids: list[str]


class _MutableSession:
    def __init__(
        self,
        *,
        problem_spec: ProblemSpec,
        root_node: Node,
        budget_spent: int,
        step_count: int,
        island_policies: Sequence[SearchIslandPolicy],
    ) -> None:
        self.problem_spec = problem_spec
        self.root_id = root_node.node_id
        self.nodes: dict[str, Node] = {root_node.node_id: root_node}
        self.archive_ids: list[str] = [root_node.node_id]
        self.frontier_ids: list[str] = [root_node.node_id]
        self.pruned_ids: list[str] = []
        self.winner_ids: list[str] = []
        self.islands: dict[str, _MutableIslandState] = {
            policy.island_id: _MutableIslandState(
                policy=policy,
                archive_ids=[root_node.node_id],
                frontier_ids=[root_node.node_id],
                pruned_ids=[],
            )
            for policy in island_policies
        }
        self.learning_notes: list[LearningNote] = []
        self.reusable_learning_notes: list[ReusableLearningNote] = []
        self.budget_spent = budget_spent
        self.step_count = step_count
        self._next_node_index = 2

    @property
    def root_node(self) -> Node:
        return self.nodes[self.root_id]

    @property
    def island_ids(self) -> list[str]:
        return list(self.islands)

    def island_order(self, island_id: str) -> int:
        return self.island_ids.index(island_id)

    def island_policy(self, island_id: str) -> SearchIslandPolicy:
        return self.islands[island_id].policy

    def island_prompt(self, island_id: str) -> dict[str, JSONValue]:
        return self.island_policy(island_id).to_prompt_dict()

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

    def archive(self, node_id: str, *, island_id: str | None) -> None:
        _append_unique(self.archive_ids, node_id)
        if island_id is not None:
            _append_unique(self.islands[island_id].archive_ids, node_id)

    def mark_pruned(self, node_id: str, *, island_id: str | None) -> None:
        _append_unique(self.pruned_ids, node_id)
        if island_id is not None:
            _append_unique(self.islands[island_id].pruned_ids, node_id)

    def set_learning_notes(self, notes: Sequence[LearningNote]) -> None:
        self.learning_notes = list(notes)

    def set_reusable_learning_notes(
        self,
        notes: Sequence[ReusableLearningNote],
    ) -> None:
        self.reusable_learning_notes = list(notes)

    def rank_island_nodes(self, island_id: str) -> list[Node]:
        island = self.islands[island_id]
        candidates = [
            self.nodes[node_id]
            for node_id in island.frontier_ids
            if node_id in self.nodes and _is_rankable(self.nodes[node_id])
        ]
        if not candidates:
            candidates = [
                self.nodes[node_id]
                for node_id in island.archive_ids
                if node_id in self.nodes and _is_rankable(self.nodes[node_id])
            ]
        if not candidates:
            return []
        return _rank_nodes_for_island(candidates, island.policy)

    def refresh_frontier(self, *, limit: int) -> None:
        per_island_limits = _allocate_targets(limit, len(self.island_ids))
        self.frontier_ids = []
        for island_id, island_limit in zip(self.island_ids, per_island_limits):
            island = self.islands[island_id]
            if island_limit <= 0:
                island.frontier_ids = []
                continue

            candidates = [
                self.nodes[node_id]
                for node_id in island.archive_ids
                if node_id in self.nodes and _is_rankable(self.nodes[node_id])
            ]
            if not candidates:
                island.frontier_ids = [self.root_id]
            else:
                ranked = _rank_nodes_for_island(candidates, island.policy)
                frontier: list[str] = []
                for node in ranked[:island_limit]:
                    _append_unique(frontier, node.node_id)

                most_novel = max(
                    candidates,
                    key=lambda node: (node.novelty_score, node.score.total_score),
                )
                _append_unique(frontier, most_novel.node_id)

                most_uncertain = min(
                    candidates,
                    key=lambda node: (
                        node.score.confidence_estimate,
                        -node.novelty_score,
                    ),
                )
                _append_unique(frontier, most_uncertain.node_id)
                island.frontier_ids = frontier[:island_limit]
            for node_id in island.frontier_ids:
                _append_unique(self.frontier_ids, node_id)

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
            islands={
                island_id: island.policy.to_search_island(
                    archive_ids=island.archive_ids,
                    frontier_ids=island.frontier_ids,
                    pruned_ids=island.pruned_ids,
                )
                for island_id, island in self.islands.items()
            },
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
        self._lock = Lock()
        self._invocations: dict[tuple[str, str], int] = defaultdict(int)
        self._provider_failures: dict[tuple[str, str], int] = defaultdict(int)
        self._critiques: dict[tuple[str, str], tuple[int, int]] = {}
        self._learning_note_counts: dict[tuple[str, str], int] = defaultdict(int)

    def record_invocation(self, *, action_name: str, provider_name: str | None = None) -> None:
        with self._lock:
            self._invocations[self._key(action_name, provider_name)] += 1

    def record_provider_failure(
        self,
        *,
        action_name: str,
        provider_name: str | None = None,
    ) -> None:
        with self._lock:
            self._provider_failures[self._key(action_name, provider_name)] += 1

    def record_critique(
        self,
        *,
        action_name: str,
        provider_name: str | None = None,
        useful: bool,
    ) -> None:
        with self._lock:
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
        with self._lock:
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


def _allocate_targets(total: int, count: int) -> list[int]:
    if count <= 0:
        return []
    normalized_total = max(total, 0)
    base, remainder = divmod(normalized_total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _rank_nodes_for_island(
    nodes: Sequence[Node],
    island_policy: SearchIslandPolicy,
) -> list[Node]:
    if island_policy.selection_mode == "balanced":
        return rank_nodes(nodes)
    return sorted(
        nodes,
        key=lambda node: _stage_priority_key(node, island_policy),
        reverse=True,
    )


def _stage_priority_key(
    node: Node,
    island_policy: SearchIslandPolicy,
) -> tuple[float, ...]:
    if node.score is None:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    if island_policy.selection_mode == "conservative":
        return (
            node.score.implementation_tractability,
            node.score.plausibility,
            node.score.adversarial_robustness,
            node.score.confidence_estimate,
            node.score.total_score,
        )
    if island_policy.selection_mode == "upside":
        return (
            node.score.upside,
            node.novelty_score,
            node.score.distinctiveness,
            node.score.total_score,
            node.score.confidence_estimate,
        )
    return (
        node.score.total_score,
        node.novelty_score,
        node.score.adversarial_robustness,
        node.score.usefulness,
        node.score.confidence_estimate,
    )


def _node_snapshot_payload(node: Node) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "node_id": node.node_id,
        "action_type": node.action_type.value,
        "candidate": node.candidate.to_dict(),
        "novelty_score": node.novelty_score,
        "lifecycle_status": node.lifecycle_status.value,
    }
    if node.island_id is not None:
        payload["island_id"] = node.island_id
    if node.score is not None:
        payload["score"] = node.score.to_dict()
    if node.critique is not None:
        payload["critique"] = node.critique.to_dict()
    return payload


def _merge_novelty_assessments(
    *,
    archive_novelty: NoveltyAssessment,
    intra_batch_novelty: NoveltyAssessment,
) -> NoveltyAssessment:
    stronger_overlap = (
        intra_batch_novelty
        if intra_batch_novelty.max_similarity >= archive_novelty.max_similarity
        else archive_novelty
    )
    summary_fragments = [archive_novelty.summary]
    if intra_batch_novelty.summary != archive_novelty.summary:
        summary_fragments.append(intra_batch_novelty.summary)
    return NoveltyAssessment(
        novelty_score=min(archive_novelty.novelty_score, intra_batch_novelty.novelty_score),
        max_similarity=max(archive_novelty.max_similarity, intra_batch_novelty.max_similarity),
        nearest_neighbor_id=stronger_overlap.nearest_neighbor_id,
        similarity_threshold=max(
            archive_novelty.similarity_threshold,
            intra_batch_novelty.similarity_threshold,
        ),
        is_novel=archive_novelty.is_novel and intra_batch_novelty.is_novel,
        summary=" ".join(summary_fragments),
        duplicate_signals=_collect_unique_strings(
            [
                *archive_novelty.duplicate_signals,
                *intra_batch_novelty.duplicate_signals,
            ],
            limit=6,
        ),
    )


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
    islands: dict[str, SearchIsland],
    best: Node,
    conservative: Node,
    high_upside: Node,
    rejected: Sequence[Node],
    learning_notes: Sequence[LearningNote],
    next_experiments: Sequence[str],
    assumptions: Sequence[str],
    failure_modes: Sequence[str],
    reversal_conditions: Sequence[str],
    selection_checks: Sequence[str],
) -> str:
    lines = [
        "# Argus Recommendation",
        "",
        "## Refined Problem Frame",
        problem_spec.request,
        "",
    ]
    if islands:
        lines.append("## Search Islands")
        for island in islands.values():
            lines.append(
                f"- {island.label} (`{island.island_id}`): {island.description} "
                f"[archive={len(island.archive_ids)}, frontier={len(island.frontier_ids)}, pruned={len(island.pruned_ids)}]"
            )
        lines.append("")
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
            f"- Island: {_node_island_label(best, islands)}",
            f"- Mechanism: {best.candidate.mechanism}",
            "",
            "## Conservative Option",
            f"{conservative.candidate.thesis} (`{conservative.node_id}`)",
            f"- Island: {_node_island_label(conservative, islands)}",
            f"- Mechanism: {conservative.candidate.mechanism}",
            "",
            "## High-Upside Option",
            f"{high_upside.candidate.thesis} (`{high_upside.node_id}`)",
            f"- Island: {_node_island_label(high_upside, islands)}",
            f"- Mechanism: {high_upside.candidate.mechanism}",
            "",
            "## Rejected But Insightful",
        ]
    )
    if rejected:
        for node in rejected:
            lines.append(
                f"- `{node.node_id}` ({_node_island_label(node, islands)}): {node.candidate.thesis}"
            )
    else:
        lines.append("- None.")
    lines.append("")

    if selection_checks:
        lines.append("## Pairwise Selection Checks")
        for check in selection_checks:
            lines.append(f"- {check}")
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


def _pairwise_selection_notes(records: Sequence[_PairwiseDecisionRecord]) -> list[str]:
    notes: list[str] = []
    for record in records:
        loser_node_id = (
            record.right_node_id
            if record.winner_node_id == record.left_node_id
            else record.left_node_id
        )
        fragments = [
            f"{record.selection_label}: `{record.winner_node_id}` beat `{loser_node_id}`.",
            record.assessment.summary,
        ]
        if record.assessment.decisive_advantages:
            fragments.append(f"Key edge: {record.assessment.decisive_advantages[0]}")
        if record.assessment.decisive_risks:
            fragments.append(f"Main risk: {record.assessment.decisive_risks[0]}")
        notes.append(" ".join(fragments))
    return notes


def _node_island_label(node: Node, islands: dict[str, SearchIsland]) -> str:
    if node.island_id is None:
        return "Shared"
    island = islands.get(node.island_id)
    return island.label if island is not None else node.island_id


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
