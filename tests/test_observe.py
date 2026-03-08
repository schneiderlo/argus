from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from argus.config import ArgusConfig
from argus.models import (
    ActionType,
    Candidate,
    Critique,
    FinalRecommendation,
    LearningMemory,
    LearningNoteType,
    Node,
    NodeLifecycleStatus,
    ProblemSpec,
    ProviderRoutingStats,
    ProviderRoutingStatsEntry,
    ReusableLearningNote,
    ScoreVector,
    SearchState,
)
from argus.observe import (
    _annotate_nodes_with_termination_reason,
    _memory_payload,
    _node_termination_reason,
    _state_payload,
    _status_payload,
)
from argus.storage import PersistedRun, RunManifest, RunStatus


class ObserverTerminationReasonTests(unittest.TestCase):
    def test_rejected_node_prefers_novelty_summary(self) -> None:
        reason = _node_termination_reason(
            {
                "lifecycle_status": NodeLifecycleStatus.REJECTED.value,
                "metadata": {
                    "novelty": {
                        "summary": "Near-duplicate of node-0001 with matching mechanism and rollout.",
                    }
                },
            }
        )
        self.assertEqual(
            reason,
            (
                "Rejected by novelty gate: Near-duplicate of node-0001 "
                "with matching mechanism and rollout."
            ),
        )

    def test_rejected_node_falls_back_to_similarity_details(self) -> None:
        reason = _node_termination_reason(
            {
                "lifecycle_status": NodeLifecycleStatus.REJECTED.value,
                "metadata": {
                    "novelty": {
                        "nearest_neighbor_id": "node-0001",
                        "max_similarity": 0.95,
                    }
                },
            }
        )
        self.assertEqual(
            reason,
            "Rejected by novelty gate due to near-duplicate overlap with node-0001 (similarity 0.95).",
        )

    def test_failed_node_uses_hard_constraint_reasons(self) -> None:
        reason = _node_termination_reason(
            {
                "lifecycle_status": NodeLifecycleStatus.FAILED.value,
                "score": {
                    "hard_constraint_reasons": [
                        "Exceeds memory envelope.",
                        "Cannot meet latency bound.",
                    ]
                },
            }
        )
        self.assertEqual(
            reason,
            "Failed hard constraints: Exceeds memory envelope.; Cannot meet latency bound.",
        )

    def test_pruned_node_has_manual_reason(self) -> None:
        reason = _node_termination_reason(
            {"lifecycle_status": NodeLifecycleStatus.PRUNED.value}
        )
        self.assertEqual(reason, "Terminated manually by operator.")

    def test_annotation_adds_reason_for_terminal_nodes_only(self) -> None:
        payload = {
            "node-0001": {
                "lifecycle_status": NodeLifecycleStatus.ADMITTED.value,
                "metadata": {},
            },
            "node-0002": {
                "lifecycle_status": NodeLifecycleStatus.REJECTED.value,
                "metadata": {
                    "novelty": {"summary": "Near-duplicate of node-0001."},
                },
            },
        }
        annotated = _annotate_nodes_with_termination_reason(payload)
        self.assertIsInstance(annotated, dict)
        self.assertNotIn("termination_reason", annotated["node-0001"])
        self.assertEqual(
            annotated["node-0002"]["termination_reason"],
            "Rejected by novelty gate: Near-duplicate of node-0001.",
        )


class ObserverPayloadTests(unittest.TestCase):
    def test_memory_payload_uses_current_typed_ledgers(self) -> None:
        store = _MemoryStoreStub()

        payload = _memory_payload(store)

        self.assertEqual(payload["routing_stats"]["entries"][0]["provider_name"], "codex")
        self.assertEqual(payload["routing_stats"]["entries"][0]["action_name"], "rank")
        self.assertEqual(
            payload["learning_memory"]["entries"][0]["source_run_ids"],
            ["run-observer-fixture"],
        )
        self.assertEqual(
            payload["learning_memory"]["entries"][0]["evidence_sources"],
            ["search_run"],
        )

    def test_state_payload_includes_final_artifacts_and_annotations(self) -> None:
        persisted_run = _sample_persisted_run()

        payload = _state_payload(persisted_run)

        self.assertEqual(payload["manifest"]["status"], RunStatus.COMPLETED.value)
        self.assertEqual(
            payload["final_recommendation"]["best_bet_node_id"],
            "node-0001",
        )
        self.assertEqual(payload["summary_markdown"], "## Recommendation\nPrefer node-0001.")
        self.assertEqual(payload["routing_summary"]["entries"][0]["provider_name"], "codex")
        self.assertEqual(
            payload["nodes"]["node-0002"]["termination_reason"],
            "Rejected by novelty gate: Near-duplicate of node-0001.",
        )
        self.assertEqual(payload["winner_ids"], ["node-0001"])

    def test_state_payload_returns_empty_object_without_state(self) -> None:
        problem_spec = ProblemSpec(request="Audit the observer payload.")
        manifest = RunManifest(
            run_id="run-empty-observer",
            provider_name="codex",
            budget=4,
            status=RunStatus.RUNNING,
            created_at=datetime(2026, 3, 8, 13, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 8, 13, 0, tzinfo=timezone.utc),
        )
        persisted_run = PersistedRun(
            path=Path("/tmp/run-empty-observer"),
            manifest=manifest,
            problem_spec=problem_spec,
            state=None,
        )

        self.assertEqual(_state_payload(persisted_run), {})

    def test_status_payload_uses_run_status_summary_shape(self) -> None:
        with unittest.mock.patch(
            "argus.observe.build_run_status_summary"
        ) as build_summary:
            build_summary.return_value = unittest.mock.Mock(
                to_dict=unittest.mock.Mock(
                    return_value={
                        "run_id": "run-observer-fixture",
                        "status": "running",
                        "current_action": "deepen",
                        "active_provider_invocation_count": 1,
                    }
                )
            )

            payload = _status_payload(
                ArgusConfig.discover(Path("/tmp/argus-status-payload")),
                run_id="run-observer-fixture",
            )

        self.assertEqual(payload["run_id"], "run-observer-fixture")
        self.assertEqual(payload["current_action"], "deepen")
        self.assertEqual(payload["active_provider_invocation_count"], 1)


class ObserverReportSourceTests(unittest.TestCase):
    def test_report_route_uses_typed_winner_fields_not_legacy_manifest_winner_id(self) -> None:
        route_path = (
            Path(__file__).resolve().parents[1]
            / "src/argus/render/ui/src/routes/runs/[id]/report/+page.svelte"
        )

        source = route_path.read_text(encoding="utf-8")

        self.assertIn("best_bet_node_id", source)
        self.assertIn("winner_ids?.[0]", source)
        self.assertNotIn("manifest?.winner_id", source)

    def test_report_route_renders_summary_markdown_as_html(self) -> None:
        route_path = (
            Path(__file__).resolve().parents[1]
            / "src/argus/render/ui/src/routes/runs/[id]/report/+page.svelte"
        )
        markdown_renderer_path = (
            Path(__file__).resolve().parents[1]
            / "src/argus/render/ui/src/lib/markdown.ts"
        )

        route_source = route_path.read_text(encoding="utf-8")
        renderer_source = markdown_renderer_path.read_text(encoding="utf-8")

        self.assertIn("renderRichMarkdown", route_source)
        self.assertIn("{@html summaryHtml()}", route_source)
        self.assertIn("export function renderRichMarkdown", renderer_source)

    def test_observer_graph_route_uses_status_and_events_api(self) -> None:
        route_path = (
            Path(__file__).resolve().parents[1]
            / "src/argus/render/ui/src/routes/runs/[id]/+page.svelte"
        )

        source = route_path.read_text(encoding="utf-8")

        self.assertIn("fetchRunStatus", source)
        self.assertIn("fetchRunEvents", source)
        self.assertIn("EventTape", source)

    def test_report_route_auto_refreshes_while_running(self) -> None:
        route_path = (
            Path(__file__).resolve().parents[1]
            / "src/argus/render/ui/src/routes/runs/[id]/report/+page.svelte"
        )

        source = route_path.read_text(encoding="utf-8")

        self.assertIn("fetchRunStatus", source)
        self.assertIn("setInterval", source)
        self.assertIn("refreshes automatically", source)

    def test_top_bar_uses_search_budget_label(self) -> None:
        component_path = (
            Path(__file__).resolve().parents[1]
            / "src/argus/render/ui/src/lib/components/TopBar.svelte"
        )

        source = component_path.read_text(encoding="utf-8")

        self.assertIn("Search Budget", source)
        self.assertNotIn("Token Budget", source)


def _sample_problem_spec() -> ProblemSpec:
    return ProblemSpec(
        request="Design a replayable observer report for Argus runs.",
        constraints=["Use persisted run artifacts only."],
        success_criteria=["Expose the winning recommendation and reusable memory."],
    )


def _sample_nodes() -> dict[str, Node]:
    created_at = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
    return {
        "node-0001": Node(
            node_id="node-0001",
            parent_ids=[],
            depth=0,
            action_type=ActionType.FRAME_PROBLEM,
            provider_name="codex",
            candidate=Candidate(
                thesis="Expose the persisted final recommendation directly in observer state.",
                mechanism="Read the run snapshot and return final recommendation, summary, and routing metadata alongside the search state.",
                strengths=["Matches the typed storage contract."],
                evidence=["Run snapshots already persist these artifacts."],
            ),
            score=ScoreVector(
                hard_constraint_pass=True,
                distinctiveness=0.82,
                usefulness=0.91,
                specificity=0.88,
                plausibility=0.9,
                implementation_tractability=0.93,
                upside=0.74,
                adversarial_robustness=0.81,
                evidence_quality=0.86,
                total_score=0.86,
                confidence_estimate=0.89,
            ),
            critique=Critique(
                hidden_dependencies=["Observer pages must switch to the new fields."],
                kill_shots=[],
                sharp_edges=["UI verification is separate from Python verification."],
                summary="Strong fit because it removes legacy contract assumptions.",
            ),
            novelty_score=0.79,
            lifecycle_status=NodeLifecycleStatus.WINNER,
            metadata={},
            created_at=created_at,
        ),
        "node-0002": Node(
            node_id="node-0002",
            parent_ids=["node-0001"],
            depth=1,
            action_type=ActionType.MUTATE,
            provider_name="codex",
            candidate=Candidate(
                thesis="Keep a compatibility shim that reintroduces winner_id.",
                mechanism="Duplicate the current payload into an older shape for the UI.",
                failure_modes=["Drifts again as the typed backend evolves."],
                evidence=["This mismatch already happened once."],
            ),
            novelty_score=0.08,
            lifecycle_status=NodeLifecycleStatus.REJECTED,
            metadata={"novelty": {"summary": "Near-duplicate of node-0001."}},
            created_at=created_at,
        ),
    }


def _sample_state() -> SearchState:
    problem_spec = _sample_problem_spec()
    return SearchState(
        problem_spec=problem_spec,
        root_id="node-0001",
        nodes=_sample_nodes(),
        archive_ids=["node-0001", "node-0002"],
        frontier_ids=[],
        pruned_ids=[],
        winner_ids=["node-0001"],
        learning_notes=[],
        budget_spent=3,
        step_count=2,
    )


def _sample_persisted_run() -> PersistedRun:
    timestamp = datetime(2026, 3, 8, 12, 5, tzinfo=timezone.utc)
    problem_spec = _sample_problem_spec()
    state = _sample_state()
    return PersistedRun(
        path=Path("/tmp/run-observer-fixture"),
        manifest=RunManifest(
            run_id="run-observer-fixture",
            provider_name="codex",
            budget=6,
            status=RunStatus.COMPLETED,
            created_at=timestamp,
            updated_at=timestamp,
            state_path="state.json",
            learning_notes_path="learning-notes.json",
            final_recommendation_path="final-recommendation.json",
            summary_path="summary.md",
        ),
        problem_spec=problem_spec,
        state=state,
        final_recommendation=FinalRecommendation(
            best_bet_node_id="node-0001",
            conservative_node_id=None,
            high_upside_node_id=None,
            rejected_but_insightful_ids=["node-0002"],
            summary_markdown="## Recommendation\nPrefer node-0001.",
            next_experiments=["Confirm the Svelte report consumes the typed payload."],
            assumptions=["The observer report should reflect persisted artifacts."],
            failure_modes=["The frontend may still expect the legacy shape."],
            reversal_conditions=["A future API version deliberately changes the observer contract."],
        ),
        summary_markdown="## Recommendation\nPrefer node-0001.",
        routing_summary=ProviderRoutingStats(
            entries=[
                ProviderRoutingStatsEntry(
                    provider_name="codex",
                    action_name="rank",
                    run_count=1,
                    invocation_count=2,
                    candidate_count=2,
                    scored_node_count=2,
                    admitted_count=1,
                    rejected_count=1,
                    winner_count=1,
                    winner_contribution_count=1,
                    critique_count=1,
                    useful_critique_count=1,
                    learning_note_count=1,
                    accumulated_score=1.72,
                    total_reward=1.2,
                    last_run_id="run-observer-fixture",
                    last_updated_at=timestamp,
                )
            ],
            updated_at=timestamp,
        ),
    )


class _MemoryStoreStub:
    def load_learning_memory(self) -> LearningMemory:
        timestamp = datetime(2026, 3, 8, 12, 10, tzinfo=timezone.utc)
        return LearningMemory(
            entries=[
                ReusableLearningNote(
                    note_id="winning_pattern:observer-contract",
                    note_type=LearningNoteType.WINNING_PATTERN,
                    text="Observer views stay stable when they read the typed persisted artifacts directly.",
                    source_run_ids=["run-observer-fixture"],
                    source_node_refs=["run-observer-fixture:node-0001"],
                    problem_statements=["Design a replayable observer report for Argus runs."],
                    observation_count=2,
                    first_seen_at=timestamp,
                    last_seen_at=timestamp,
                )
            ],
            updated_at=timestamp,
        )

    def load_provider_routing_stats(self) -> ProviderRoutingStats:
        timestamp = datetime(2026, 3, 8, 12, 10, tzinfo=timezone.utc)
        return ProviderRoutingStats(
            entries=[
                ProviderRoutingStatsEntry(
                    provider_name="codex",
                    action_name="rank",
                    run_count=2,
                    invocation_count=3,
                    candidate_count=4,
                    scored_node_count=4,
                    admitted_count=2,
                    rejected_count=1,
                    winner_count=1,
                    winner_contribution_count=2,
                    critique_count=2,
                    useful_critique_count=1,
                    learning_note_count=1,
                    accumulated_score=2.4,
                    total_reward=1.5,
                    last_run_id="run-observer-fixture",
                    last_updated_at=timestamp,
                )
            ],
            updated_at=timestamp,
        )


if __name__ == "__main__":
    unittest.main()
