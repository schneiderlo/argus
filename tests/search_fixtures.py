from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import time

from argus.benchmarks import BenchmarkRuntimeMode
from argus.errors import ArgusValidationError
from argus.models import (
    ActionType,
    AdversarialReview,
    Candidate,
    ComparisonMatrix,
    ComparisonMatrixRow,
    CoverageLedger,
    CoverageStatus,
    Critique,
    DeepDiveDoc,
    FinalDecisionDoc,
    HybridAssessment,
    HybridVerdict,
    LearningNote,
    LearningNoteType,
    ProblemSpec,
    ProposalBrief,
    ProposalDisposition,
    ProposalTriageDecision,
    SearchAxis,
    SearchCell,
    SearchSpaceFrame,
    TriageReport,
)
from argus.providers import ProviderArtifacts, ProviderResponse
from argus.search.contracts import (
    CandidateBatch,
    HybridCandidateBatch,
    HybridCandidateDecision,
    LearningCompression,
    ProblemFrame,
)
from argus.search.research_contracts import FinalDecisionPackage, ProposalSeedBatch, SearchSpacePlan


class SearchFixtureProvider:
    def __init__(
        self,
        root_dir: Path,
        *,
        name: str = "fixture",
        fail_on_action: str | None = None,
        fail_actions: set[str] | None = None,
        sleep_by_action: dict[str, float] | None = None,
        seed_candidates: list[Candidate] | None = None,
        seed_candidates_by_island: dict[str, list[Candidate]] | None = None,
    ) -> None:
        self.root_dir = root_dir
        self.name = name
        normalized_fail_actions = set(fail_actions or set())
        if fail_on_action is not None:
            normalized_fail_actions.add(fail_on_action)
        self.fail_actions = normalized_fail_actions
        self.sleep_by_action = dict(sleep_by_action or {})
        if seed_candidates is not None and not seed_candidates:
            raise ArgusValidationError("seed_candidates must not be empty when provided.")
        if seed_candidates_by_island is not None:
            normalized_seed_candidates_by_island: dict[str, list[Candidate]] = {}
            for island_id, candidates in seed_candidates_by_island.items():
                if not candidates:
                    raise ArgusValidationError(
                        "seed_candidates_by_island entries must not be empty."
                    )
                normalized_seed_candidates_by_island[island_id] = list(candidates)
            self.seed_candidates_by_island = normalized_seed_candidates_by_island
        else:
            self.seed_candidates_by_island = None
        self.seed_candidates = None if seed_candidates is None else list(seed_candidates)
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()
        self._next_call_index = 1

    def run_action(
        self,
        *,
        action_name: ActionType | str,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
        output_schema,
    ):
        normalized_action = action_name.value if isinstance(action_name, ActionType) else action_name
        started_at = time.monotonic()
        with self._lock:
            call_index = self._next_call_index
            self._next_call_index += 1
            call_record = {
                "call_index": call_index,
                "action_name": normalized_action,
                "problem_spec": problem_spec,
                "input_payload": input_payload,
                "started_at": started_at,
            }
            self.calls.append(call_record)

        try:
            delay = self.sleep_by_action.get(normalized_action, 0.0)
            if delay > 0:
                time.sleep(delay)

            if normalized_action in self.fail_actions:
                raise ArgusValidationError(f"fixture provider failed during {normalized_action}.")

            handler = getattr(self, f"_handle_{normalized_action}")
            payload = handler(problem_spec, input_payload)
            raw_payload = payload.to_dict() if hasattr(payload, "to_dict") else payload
            typed_payload = output_schema.validate(raw_payload)

            artifacts_dir = self.root_dir / normalized_action / f"call-{call_index:02d}"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifacts = ProviderArtifacts(
                invocation_id=f"{normalized_action}-{call_index:02d}",
                invocation_dir=artifacts_dir,
                prompt_path=artifacts_dir / "prompt.md",
                schema_path=artifacts_dir / "schema.json",
                last_message_path=artifacts_dir / "last-message.json",
                response_path=artifacts_dir / "response.json",
                stdout_path=artifacts_dir / "stdout.jsonl",
                stderr_path=artifacts_dir / "stderr.txt",
                metadata_path=artifacts_dir / "metadata.json",
                sandbox_dir=artifacts_dir / "workspace",
                failure_path=artifacts_dir / "failure.json",
            )
            artifacts.sandbox_dir.mkdir(parents=True, exist_ok=True)
            return ProviderResponse(
                provider_name=self.name,
                action_name=normalized_action,
                payload=typed_payload,
                raw_payload=raw_payload,
                prompt_sha256=f"fixture-{normalized_action}",
                artifacts=artifacts,
                exit_status=0,
                timestamp=datetime(2026, 3, 6, 3, 33, 40, tzinfo=timezone.utc),
                model="fixture-model",
            )
        finally:
            with self._lock:
                call_record["finished_at"] = time.monotonic()

    def _handle_frame_problem(
        self,
        problem_spec: ProblemSpec,
        input_payload: dict[str, object],
    ) -> ProblemFrame:
        request = str(input_payload["request"])
        return ProblemFrame(
            problem_spec=ProblemSpec(
                request=request,
                constraints=["Stay self-serve.", "Keep every decision auditable."],
                success_criteria=[
                    "Produce clearly differentiated strategic bets.",
                    "Leave behind replayable artifacts and explicit tradeoffs.",
                ],
                context={"segment": "product"},
            ),
            framing_candidate=Candidate(
                thesis="Frame the search around durable workflow lock-in rather than decorative brainstorming.",
                mechanism=(
                    "Bias the search toward mechanisms that become part of a repeated team ritual "
                    "and leave behind inspectable artifacts."
                ),
                assumptions=["The operator values actionability over stylistic novelty."],
                strengths=["Keeps the search focused on decision quality and replayability."],
                failure_modes=["Could underrate a genuinely novel idea that is hard to operationalize."],
                unknowns=["Which repeated team ritual has the strongest retention leverage?"],
                implementation_shape="Use evaluator-first search with archived stepping stones.",
                evidence=["The repo specs prioritize evaluator-first, replayable decision artifacts."],
            ),
            framing_notes=[
                "Bias toward repeated operational use, not one-off ideation.",
                "Reject ideas that cannot survive audit and replay.",
            ],
        )

    def _handle_generate_seed(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> CandidateBatch:
        target_count = int(input_payload["target_count"])
        island_payload = input_payload.get("island")
        island_id = None
        if isinstance(island_payload, dict):
            raw_island_id = island_payload.get("island_id")
            if isinstance(raw_island_id, str):
                island_id = raw_island_id
        templates: list[Candidate]
        if (
            island_id is not None
            and self.seed_candidates_by_island is not None
            and island_id in self.seed_candidates_by_island
        ):
            templates = list(self.seed_candidates_by_island[island_id])
        elif self.seed_candidates is not None:
            templates = list(self.seed_candidates)
        else:
            templates = [
                _workflow_archive_candidate(),
                _operational_assistant_candidate(),
                _benchmark_market_candidate(),
                _chat_wrapper_candidate(),
            ]
        candidates = [templates[index % len(templates)] for index in range(target_count)]
        return CandidateBatch(
            candidates=candidates,
            batch_summary="Generated a balanced seed set spanning safe, bold, and obviously weak directions.",
        )

    def _handle_frame_search_space(
        self,
        problem_spec: ProblemSpec,
        _: dict[str, object],
    ) -> SearchSpacePlan:
        frame = SearchSpaceFrame(
            frame_id="frame-001",
            problem_statement=problem_spec.request,
            target_decision="Choose the default Argus research runtime to ship next.",
            hard_gates=[
                "Must keep deterministic filesystem-backed persistence.",
                "Must produce auditable decision-grade artifacts.",
            ],
            soft_criteria=[
                "Decision quality",
                "Operator trust",
                "Latency discipline",
            ],
            baseline_options=["Keep the adaptive node runtime as the default control."],
            axes=[
                SearchAxis(
                    axis_id="coverage",
                    label="Coverage strategy",
                    description="How explicitly the runtime plans coverage of the search space.",
                    options=["implicit frontier", "explicit ledger"],
                ),
                SearchAxis(
                    axis_id="authoring",
                    label="Authoring depth",
                    description="How much structured decision authoring surviving families receive.",
                    options=["summary finish", "decision dossier"],
                ),
            ],
            coverage_plan=[
                "Seed one representative for each materially different family worth comparing.",
                "Deepen and red-team any family that remains viable after triage.",
            ],
            notes=["Keep the adaptive runtime available as the benchmark control path."],
        )
        ledger = CoverageLedger(
            ledger_id="ledger-001",
            frame_id=frame.frame_id,
            cells=[
                SearchCell(
                    cell_id="cell-control",
                    label="Implicit frontier plus richer finish",
                    axis_assignments={
                        "coverage": "implicit frontier",
                        "authoring": "summary finish",
                    },
                    hypothesis="Cheapest path, but likely still too lossy for decision-grade output.",
                    coverage_status=CoverageStatus.UNEXPLORED,
                    uncertainty=0.58,
                    hard_gate_risk=0.44,
                    evidence_strength=0.35,
                    incumbent_proposal_ids=[],
                    notes=["Represents the existing adaptive runtime plus a stronger finisher."],
                ),
                SearchCell(
                    cell_id="cell-ledger",
                    label="Coverage ledger with decision dossier",
                    axis_assignments={
                        "coverage": "explicit ledger",
                        "authoring": "decision dossier",
                    },
                    hypothesis="Higher authoring cost, but materially stronger decisions and audit trail.",
                    coverage_status=CoverageStatus.UNEXPLORED,
                    uncertainty=0.52,
                    hard_gate_risk=0.28,
                    evidence_strength=0.42,
                    incumbent_proposal_ids=[],
                ),
            ],
            coverage_summary="Both major runtime families remain worth seeding.",
            next_questions=["Does the explicit-ledger path improve decision quality enough to justify the extra authoring?"],
            updated_at=datetime(2026, 3, 8, 18, 30, 0, tzinfo=timezone.utc),
        )
        return SearchSpacePlan(search_space_frame=frame, coverage_ledger=ledger)

    def _handle_seed_cell_proposals(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> ProposalSeedBatch:
        target_cells = list(input_payload.get("target_cells", []))
        parent_node_ids = list(input_payload.get("parent_node_ids", []))
        proposals: list[ProposalBrief] = []
        for cell_payload in target_cells:
            cell_id = str(cell_payload["cell_id"])
            if cell_id == "cell-control":
                proposals.append(
                    ProposalBrief(
                        proposal_id="proposal-control",
                        cell_id=cell_id,
                        title="Adaptive runtime with stronger finish stage",
                        summary="Keep the current adaptive scheduler and add a typed decision-authoring finisher.",
                        candidate=Candidate(
                            thesis="Adaptive runtime with stronger finish stage",
                            mechanism=(
                                "Retain the adaptive node loop, but author a typed decision package only at the end."
                            ),
                            assumptions=["The current archive carries enough evidence into the finish stage."],
                            strengths=["Lower implementation cost."],
                            failure_modes=["Coverage remains under-planned."],
                            unknowns=["Whether the final stage has enough family-level evidence to choose confidently."],
                            implementation_shape="Keep search_v1 as-is and append a decision-writing step.",
                            evidence=["The current runtime already evaluates, critiques, and ranks nodes."],
                        ),
                        seed_rationale="Represents the lowest-disruption path from the current implementation.",
                        open_questions=["Can the finisher compensate for missing explicit coverage state?"],
                        evidence=["Useful as the benchmark control."],
                        parent_node_ids=parent_node_ids,
                    )
                )
                continue
            proposals.append(
                ProposalBrief(
                    proposal_id="proposal-ledger",
                    cell_id=cell_id,
                    title="Coverage-led research runtime",
                    summary="Default to explicit search-space framing, coverage-led triage, and decision-grade artifacts.",
                    candidate=Candidate(
                        thesis="Coverage-led research runtime",
                        mechanism=(
                            "Frame the search space explicitly, seed important cells, triage at the family level, "
                            "deepen survivors, red-team them, and write the final decision from the full artifact bundle."
                        ),
                        assumptions=["The operator values stronger decision quality enough to accept more authoring work."],
                        strengths=["Best audit trail and strongest decision package."],
                        failure_modes=["Authoring latency could grow too quickly."],
                        unknowns=["How much concurrent authoring keeps the path fast enough?"],
                        implementation_shape="Persist a typed research bundle and render per-artifact markdown under the run directory.",
                        evidence=["The specs explicitly require coverage-led planning and typed decision artifacts."],
                    ),
                    seed_rationale="Matches the main product gap called out by the specs and fix plan.",
                    open_questions=["Can the richer authoring path stay within the standard cost profile?"],
                    evidence=["Directly addresses the missing coverage-led runtime."],
                    parent_node_ids=parent_node_ids,
                )
            )
        return ProposalSeedBatch(
            proposals=proposals,
            batch_summary="Seeded both the control path and the coverage-led research path for direct comparison.",
        )

    def _handle_triage_proposals(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> TriageReport:
        proposals = list(input_payload["proposals"])
        proposal_ids = [str(proposal["proposal_id"]) for proposal in proposals]
        decisions: list[ProposalTriageDecision] = []
        survivor_ids: list[str] = []
        for proposal_id in proposal_ids:
            if proposal_id == "proposal-ledger":
                decisions.append(
                    ProposalTriageDecision(
                        proposal_id=proposal_id,
                        disposition=ProposalDisposition.SURVIVE,
                        rationale="Best match for explicit coverage planning and decision-grade output requirements.",
                        follow_up="Deepen the runtime design and attack its latency risks.",
                    )
                )
                survivor_ids.append(proposal_id)
                continue
            decisions.append(
                ProposalTriageDecision(
                    proposal_id=proposal_id,
                    disposition=ProposalDisposition.ELIMINATE,
                    rationale="Useful benchmark control, but still too lossy to be the default product path.",
                    follow_up="Keep it as a benchmark mode rather than the default runtime.",
                )
            )
        return TriageReport(
            report_id="triage-001",
            frame_id=str(input_payload["frame_id"]),
            decisions=decisions,
            survivor_ids=survivor_ids,
            unexplored_cell_ids=[],
            summary="The coverage-led family survives because it closes the largest product gap.",
            next_actions=["Deepen the coverage-led family into a concrete runtime design.", "Red-team its latency and complexity risks."],
        )

    def _handle_deepen_family(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> DeepDiveDoc:
        proposal = dict(input_payload["proposal"])
        proposal_id = str(proposal["proposal_id"])
        return DeepDiveDoc(
            doc_id=f"deep-{proposal_id}",
            proposal_id=proposal_id,
            title=str(proposal["title"]),
            executive_summary="Separate coverage-aware scheduling from artifact authoring and persist both.",
            detailed_mechanism=(
                "Create a typed search-space frame and coverage ledger, seed the highest-value uncovered cells, "
                "triage families rather than individual prose variants, then author deep dives, adversarial reviews, "
                "and a final decision doc from the full bundle."
            ),
            implementation_plan=[
                "Add research-stage provider schemas and prompts.",
                "Persist a structured research bundle plus rendered markdown artifacts under each run.",
                "Keep the adaptive runtime available as a benchmark control path.",
            ],
            key_unknowns=["Whether the richer authoring flow can stay inside the standard latency budget."],
            supporting_evidence=["The specs require explicit coverage planning and decision-grade artifacts."],
            assumptions=["Provider-backed evaluation remains the main judge layer."],
            technical_dossier_markdown=_fixture_technical_dossier_markdown(proposal_id),
        )

    def _handle_redteam_family(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> AdversarialReview:
        proposal = dict(input_payload["proposal"])
        proposal_id = str(proposal["proposal_id"])
        thesis = str(proposal["candidate"]["thesis"])
        return AdversarialReview(
            review_id=f"review-{proposal_id}",
            proposal_id=proposal_id,
            thesis_under_test=thesis,
            hidden_dependencies=["The state store must handle richer artifacts without making replay brittle."],
            failure_modes=["Serial authoring could erase the latency win from concurrent provider dispatch."],
            mitigations=["Dispatch independent deep dives and reviews concurrently, but persist the bundle in stable order."],
            summary="The proposal is viable if artifact persistence and concurrency remain disciplined.",
            verdict="Proceed, but keep latency and auditability explicit.",
            confidence=0.74,
            evidence=["The existing runtime already has bounded concurrent provider dispatch and deterministic state commits."],
        )

    def _handle_assess_hybrid(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> HybridAssessment:
        source_ids = [str(item) for item in list(input_payload["source_proposal_ids"])]
        return HybridAssessment(
            assessment_id="hybrid-001",
            source_proposal_ids=source_ids,
            hybrid_name="Coverage-led runtime with lean fallback for dominated regions",
            seam_hypothesis="Use the adaptive control path only as a bounded fallback inside clearly dominated low-value cells.",
            repaired_failure_mode="Reduce worst-case authoring latency when the coverage ledger already shows a region is low-value.",
            complementary_strengths=[
                "Coverage-led planning improves decision quality.",
                "Adaptive fallback could reduce wasted authoring effort in dominated regions.",
            ],
            complexity_tax="Introduces dual-mode scheduling and a harder operator story.",
            expected_upside="Could preserve most decision-quality gains while trimming tail latency.",
            open_questions=["Whether the seam stays auditable enough for operators to trust."],
            verdict=HybridVerdict.HOLD,
            summary="Promising, but not justified over shipping the pure coverage-led runtime first.",
        )

    def _handle_write_final_decision(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> FinalDecisionPackage:
        frame_id = str(input_payload["frame_id"])
        proposals = list(input_payload["proposals"])
        proposal_ids = [str(proposal["proposal_id"]) for proposal in proposals]
        rows: list[ComparisonMatrixRow] = []
        for proposal_id in proposal_ids:
            if proposal_id == "proposal-ledger":
                rows.append(
                    ComparisonMatrixRow(
                        proposal_id=proposal_id,
                        criterion_scores={
                            "decision_quality": 0.9,
                            "latency_discipline": 0.58,
                            "operator_auditability": 0.92,
                        },
                        advantages=["Strongest decision quality and artifact audit trail."],
                        liabilities=["Adds more authoring and persistence work."],
                        takeaway="Best default if the latency stays bounded.",
                    )
                )
                continue
            rows.append(
                ComparisonMatrixRow(
                    proposal_id=proposal_id,
                    criterion_scores={
                        "decision_quality": 0.61,
                        "latency_discipline": 0.84,
                        "operator_auditability": 0.51,
                    },
                    advantages=["Cheapest migration path from the current runtime."],
                    liabilities=["Still under-plans coverage and compresses too much into the finish stage."],
                    takeaway="Useful control benchmark, weak default.",
                )
            )
        matrix = ComparisonMatrix(
            matrix_id="matrix-001",
            frame_id=frame_id,
            criteria=["decision_quality", "latency_discipline", "operator_auditability"],
            rows=rows,
            summary="The coverage-led runtime wins on the criteria Argus most needs to improve.",
        )
        decision = FinalDecisionDoc(
            decision_id="decision-001",
            frame_id=frame_id,
            selected_proposal_id="proposal-ledger",
            runner_up_proposal_id="proposal-control" if "proposal-control" in proposal_ids else None,
            conservative_proposal_id="proposal-control" if "proposal-control" in proposal_ids else None,
            high_upside_proposal_id="proposal-ledger",
            summary="Ship the coverage-led research runtime and keep the adaptive path as the benchmark control.",
            decision_rule="Prefer the option that materially improves decision quality and auditability without violating deterministic persistence.",
            assumptions=["The richer artifact bundle remains inspectable with normal shell tools."],
            top_risks=["Authoring latency could grow until the operator no longer trusts the runtime."],
            mitigations=["Keep provider dispatch bounded and commit research artifacts in deterministic order."],
            first_spike=["Persist the research bundle and run it end to end from `argus run --runtime-mode research`."],
            kill_criteria=["If the richer bundle makes replay or verification brittle.", "If benchmarks show no material decision-quality gain."],
            next_experiments=["Benchmark the research runtime against the adaptive control path.", "Measure latency of deep-dive and red-team stages under the standard cost profile."],
            reversal_conditions=["If decision quality does not improve enough to justify the added artifact and latency overhead."],
            rejected_proposal_ids=[proposal_id for proposal_id in proposal_ids if proposal_id != "proposal-ledger"],
        )
        return FinalDecisionPackage(
            comparison_matrix=matrix,
            final_decision_doc=decision,
            decision_summary_markdown=(
                "# Argus Recommendation\n\n"
                "## Research Decision\n"
                "Ship the coverage-led research runtime and keep the adaptive path as the benchmark control.\n\n"
                "## Best Bet\n"
                "- Proposal: `Coverage-led research runtime`\n"
                "- Why it wins: strongest decision quality and audit trail.\n\n"
                "## Next Experiments\n"
                "- Benchmark the research runtime against the adaptive control path.\n"
                "- Measure latency of deep-dive and red-team stages under the standard cost profile.\n"
            ),
            decision_report_markdown=(
                "# Final Decision Memo\n\n"
                "## Recommendation\n"
                "Ship the coverage-led research runtime as the default path and retain the adaptive runtime as the control.\n\n"
                "## Why This Wins\n"
                "- It closes the biggest product gap: explicit coverage planning plus decision-grade artifacts.\n"
                "- It keeps deterministic persistence and replay intact.\n\n"
                "## Runner-Up\n"
                "The adaptive runtime remains useful as the cheaper benchmark control, but it is still too lossy for the default operator workflow.\n\n"
                "## Risks And Mitigations\n"
                "- Risk: authoring latency grows too high.\n"
                "- Mitigation: keep provider dispatch bounded and persist artifacts in deterministic order.\n\n"
                "## First Spike\n"
                "- Persist the research bundle and run it end to end from `argus run --runtime-mode research`.\n"
            ),
        )

    def _handle_judge_benchmark_modes(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        mode_outputs = list(input_payload["mode_outputs"])
        runtime_modes = [
            BenchmarkRuntimeMode(str(mode_output["runtime_mode"]))
            for mode_output in mode_outputs
        ]
        preferred_order = [
            BenchmarkRuntimeMode.RESEARCH,
            BenchmarkRuntimeMode.ADAPTIVE,
            BenchmarkRuntimeMode.STAGED,
        ]
        sorted_modes = [
            mode
            for mode in preferred_order
            if mode in runtime_modes
        ]
        if len(sorted_modes) < 2:
            raise ArgusValidationError(
                "fixture benchmark comparison requires at least two runtime modes."
            )
        winner = sorted_modes[0]
        runner_up = sorted_modes[1]
        score_map = {
            BenchmarkRuntimeMode.RESEARCH: (0.93, 0.9, 0.94, 0.91, 0.89, 0.93),
            BenchmarkRuntimeMode.ADAPTIVE: (0.76, 0.82, 0.71, 0.72, 0.79, 0.77),
            BenchmarkRuntimeMode.STAGED: (0.68, 0.7, 0.67, 0.63, 0.66, 0.67),
        }
        mode_judgments = []
        for mode_output in mode_outputs:
            runtime_mode = BenchmarkRuntimeMode(str(mode_output["runtime_mode"]))
            (
                decision_quality,
                actionability,
                tradeoff_clarity,
                risk_quality,
                experiment_quality,
                overall_score,
            ) = score_map[runtime_mode]
            mode_judgments.append(
                {
                    "runtime_mode": runtime_mode.value,
                    "decision_quality": decision_quality,
                    "actionability": actionability,
                    "tradeoff_clarity": tradeoff_clarity,
                    "risk_quality": risk_quality,
                    "experiment_quality": experiment_quality,
                    "overall_score": overall_score,
                    "strengths": [
                        f"{runtime_mode.value} exposes a clear best-bet thesis.",
                    ],
                    "weaknesses": [
                        "The artifact package still leaves some execution ambiguity."
                        if runtime_mode is not BenchmarkRuntimeMode.RESEARCH
                        else "The richer artifact set costs more authoring time."
                    ],
                    "evidence": [
                        "Used the persisted summary markdown and final recommendation package."
                    ],
                }
            )
        return {
            "winner_runtime_mode": winner.value,
            "runner_up_runtime_mode": runner_up.value,
            "summary": (
                "The research runtime wins because its artifact package makes the decision, "
                "runner-up logic, risks, and next experiment materially easier to act on."
            ),
            "confidence": 0.83,
            "decisive_reasons": [
                "The winning mode preserved clearer winner-versus-runner-up logic.",
                "Its next experiment and risk framing were more decision-grade.",
            ],
            "watchouts": [
                "The richer authoring path still needs latency discipline.",
            ],
            "mode_judgments": mode_judgments,
        }

    def _handle_assess_novelty(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        return self._novelty_payload(
            candidate_payload=dict(input_payload["candidate"]),
            archive_candidates=list(input_payload["archive_candidates"]),
            similarity_threshold=input_payload["similarity_threshold"],
        )

    def _handle_assess_novelty_batch(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "assessments": [
                self._handle_assess_novelty(
                    _,
                    {
                        "candidate": dict(candidate_payload),
                        "archive_candidates": list(input_payload["archive_candidates"]),
                        "similarity_threshold": input_payload["similarity_threshold"],
                    },
                )
                for candidate_payload in list(input_payload["candidates"])
            ]
        }

    def _novelty_payload(
        self,
        *,
        candidate_payload: dict[str, object],
        archive_candidates: list[object],
        similarity_threshold: object,
    ) -> dict[str, object]:
        candidate_thesis = str(candidate_payload["thesis"])
        for archived in archive_candidates:
            archived_thesis = str(archived["candidate"]["thesis"])
            if archived_thesis == candidate_thesis:
                return {
                    "novelty_score": 0.12,
                    "max_similarity": 0.91,
                    "nearest_neighbor_id": archived["node_id"],
                    "similarity_threshold": similarity_threshold,
                    "is_novel": False,
                    "summary": "This is a near-duplicate of an archived candidate.",
                    "duplicate_signals": ["Same thesis.", "Same mechanism family."],
                }

        if "chat wrapper" in candidate_thesis.lower():
            return {
                "novelty_score": 0.68,
                "max_similarity": 0.31,
                "nearest_neighbor_id": None,
                "similarity_threshold": similarity_threshold,
                "is_novel": True,
                "summary": "The idea is distinct, but it may still fail on quality.",
                "duplicate_signals": [],
            }

        return {
            "novelty_score": 0.86,
            "max_similarity": 0.22,
            "nearest_neighbor_id": None,
            "similarity_threshold": similarity_threshold,
            "is_novel": True,
            "summary": "The candidate is meaningfully distinct from the archive.",
            "duplicate_signals": [],
        }

    def _handle_evaluate_candidate(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        return self._evaluation_payload(Candidate.from_dict(input_payload["candidate"]))

    def _handle_evaluate_candidate_batch(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "assessments": [
                self._handle_evaluate_candidate(
                    _,
                    {
                        "candidate": dict(candidate_payload),
                    },
                )
                for candidate_payload in list(input_payload["candidates"])
            ]
        }

    def _evaluation_payload(
        self,
        candidate: Candidate,
    ) -> dict[str, object]:
        thesis = candidate.thesis.lower()
        if "chat wrapper" in thesis:
            score = _score_payload(
                hard_constraint_pass=False,
                hard_constraint_reasons=["Fails the auditability requirement."],
                distinctiveness=0.35,
                usefulness=0.22,
                specificity=0.25,
                plausibility=0.41,
                implementation_tractability=0.58,
                upside=0.28,
                adversarial_robustness=0.19,
                evidence_quality=0.15,
                total_score=2.43,
                confidence_estimate=0.74,
            )
            return {
                "score": score,
                "summary": "This is easy to describe but does not satisfy the core product bar.",
                "strengths": ["Low implementation friction."],
                "weaknesses": ["No durable artifact moat.", "Fails the auditability constraint."],
                "open_questions": ["Would this collapse into generic chat usage?"],
            }

        if "operational checklist assistant" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.61,
                usefulness=0.79,
                specificity=0.82,
                plausibility=0.86,
                implementation_tractability=0.89,
                upside=0.58,
                adversarial_robustness=0.8,
                evidence_quality=0.74,
                total_score=6.09,
                confidence_estimate=0.86,
            )
            return {
                "score": score,
                "summary": "The safest path is operationally credible and easy to trial.",
                "strengths": ["High tractability.", "Strong operational clarity."],
                "weaknesses": ["Lower upside ceiling than the strongest bets."],
                "open_questions": ["Will the checklist feel meaningfully better than existing process tooling?"],
            }

        if "peer benchmark marketplace" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.88,
                usefulness=0.73,
                specificity=0.69,
                plausibility=0.59,
                implementation_tractability=0.47,
                upside=0.95,
                adversarial_robustness=0.51,
                evidence_quality=0.56,
                total_score=5.38,
                confidence_estimate=0.63,
            )
            return {
                "score": score,
                "summary": "This has the biggest upside, but execution and trust bootstrapping are harder.",
                "strengths": ["Very high upside.", "Meaningfully differentiated."],
                "weaknesses": ["Harder to bootstrap.", "Lower confidence."],
                "open_questions": ["Can the system earn enough trust to share peer benchmarks?"],
            }

        if "lighter onboarding" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.79,
                usefulness=0.9,
                specificity=0.88,
                plausibility=0.84,
                implementation_tractability=0.83,
                upside=0.89,
                adversarial_robustness=0.76,
                evidence_quality=0.81,
                total_score=6.7,
                confidence_estimate=0.87,
            )
            return {
                "score": score,
                "summary": "The mutation keeps the moat while reducing the adoption risk.",
                "strengths": ["Strong fit plus lower onboarding risk."],
                "weaknesses": ["Still needs disciplined rollout instrumentation."],
                "open_questions": ["Will the lighter flow preserve enough differentiation?"],
            }

        if "instrumented rollout" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.83,
                usefulness=0.91,
                specificity=0.9,
                plausibility=0.86,
                implementation_tractability=0.82,
                upside=0.87,
                adversarial_robustness=0.79,
                evidence_quality=0.83,
                total_score=6.81,
                confidence_estimate=0.88,
            )
            return {
                "score": score,
                "summary": "This is the strongest overall bet because it couples the moat with a clear rollout plan.",
                "strengths": ["Best balance of usefulness, tractability, and upside."],
                "weaknesses": ["Still requires disciplined operator behavior."],
                "open_questions": ["Which rollout metric best predicts long-term retention?"],
            }

        if "paired with peer benchmarks" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.91,
                usefulness=0.86,
                specificity=0.82,
                plausibility=0.71,
                implementation_tractability=0.63,
                upside=0.94,
                adversarial_robustness=0.66,
                evidence_quality=0.74,
                total_score=6.27,
                confidence_estimate=0.75,
            )
            return {
                "score": score,
                "summary": "The combination could unlock major upside if the trust problem is solved.",
                "strengths": ["High upside with more substance than the raw marketplace idea."],
                "weaknesses": ["Operationally heavier than the best bet."],
                "open_questions": ["Can the hybrid stay simple enough for self-serve adoption?"],
            }

        if "benchmark calibration" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.87,
                usefulness=0.84,
                specificity=0.83,
                plausibility=0.72,
                implementation_tractability=0.69,
                upside=0.91,
                adversarial_robustness=0.68,
                evidence_quality=0.76,
                total_score=6.3,
                confidence_estimate=0.77,
            )
            return {
                "score": score,
                "summary": "The migrated variant preserves upside while grounding it in a stronger workflow wedge.",
                "strengths": ["Carries over the archive moat into a higher-upside framing."],
                "weaknesses": ["Still needs careful trust sequencing."],
                "open_questions": ["Will the benchmark layer stay optional long enough to avoid early friction?"],
            }

        if "archived decision evidence" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.74,
                usefulness=0.86,
                specificity=0.87,
                plausibility=0.88,
                implementation_tractability=0.89,
                upside=0.66,
                adversarial_robustness=0.83,
                evidence_quality=0.8,
                total_score=6.25,
                confidence_estimate=0.86,
            )
            return {
                "score": score,
                "summary": "The migrated conservative variant uses archived evidence to reinforce the rollout without overcomplicating it.",
                "strengths": ["Very tractable.", "Preserves a durable audit trail."],
                "weaknesses": ["Upside is still lower than the bolder archive variants."],
                "open_questions": ["How much archived context can operators absorb before the flow feels heavy?"],
            }

        if "workflow-native decision archive" in thesis:
            score = _score_payload(
                hard_constraint_pass=True,
                hard_constraint_reasons=[],
                distinctiveness=0.81,
                usefulness=0.88,
                specificity=0.84,
                plausibility=0.82,
                implementation_tractability=0.8,
                upside=0.86,
                adversarial_robustness=0.76,
                evidence_quality=0.78,
                total_score=6.55,
                confidence_estimate=0.84,
            )
            return {
                "score": score,
                "summary": "This is already strong because it compounds team knowledge into retained workflow value.",
                "strengths": ["Durable artifact moat.", "Strong alignment with the brief."],
                "weaknesses": ["Needs careful onboarding to avoid feeling heavy."],
                "open_questions": ["How fast can teams feel the retained value?"],
            }

        score = _score_payload(
            hard_constraint_pass=True,
            hard_constraint_reasons=[],
            distinctiveness=0.67,
            usefulness=0.71,
            specificity=0.69,
            plausibility=0.74,
            implementation_tractability=0.71,
            upside=0.65,
            adversarial_robustness=0.68,
            evidence_quality=0.66,
            total_score=5.51,
            confidence_estimate=0.78,
        )
        return {
            "score": score,
            "summary": "The framing direction is sound and sets up the rest of the search well.",
            "strengths": ["Keeps the search grounded."],
            "weaknesses": ["Still abstract without concrete branch candidates."],
            "open_questions": ["Which concrete branch should receive the most search budget?"],
        }

    def _handle_rank(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        objective_name = str(input_payload["objective"]["name"])
        left_payload = dict(input_payload["left"])
        right_payload = dict(input_payload["right"])
        left_candidate = Candidate.from_dict(left_payload["candidate"])
        right_candidate = Candidate.from_dict(right_payload["candidate"])
        left_thesis = left_candidate.thesis
        right_thesis = right_candidate.thesis

        if objective_name == "best_overall":
            if "instrumented rollout" in left_thesis.lower():
                return _pairwise_payload(
                    winner="left",
                    summary=(
                        "The instrumented rollout bet wins because it keeps the workflow-native moat "
                        "while proving behavior change with a tighter rollout plan."
                    ),
                    decisive_advantages=["Clearer rollout proof without giving up strategic substance."],
                    decisive_risks=["It still depends on disciplined operator follow-through."],
                    confidence=0.82,
                )
            if "instrumented rollout" in right_thesis.lower():
                return _pairwise_payload(
                    winner="right",
                    summary=(
                        "The instrumented rollout bet wins because it keeps the workflow-native moat "
                        "while proving behavior change with a tighter rollout plan."
                    ),
                    decisive_advantages=["Clearer rollout proof without giving up strategic substance."],
                    decisive_risks=["It still depends on disciplined operator follow-through."],
                    confidence=0.82,
                )

        if objective_name == "conservative_option":
            if left_thesis == "Operational checklist assistant":
                return _pairwise_payload(
                    winner="left",
                    summary=(
                        "The original checklist assistant is the safer option because it narrows the "
                        "surface area and keeps the rollout simpler than the deeper variants."
                    ),
                    decisive_advantages=["Lowest operational complexity among the viable options."],
                    decisive_risks=["Its moat ceiling is lower than the archive-centered bets."],
                    confidence=0.8,
                )
            if right_thesis == "Operational checklist assistant":
                return _pairwise_payload(
                    winner="right",
                    summary=(
                        "The original checklist assistant is the safer option because it narrows the "
                        "surface area and keeps the rollout simpler than the deeper variants."
                    ),
                    decisive_advantages=["Lowest operational complexity among the viable options."],
                    decisive_risks=["Its moat ceiling is lower than the archive-centered bets."],
                    confidence=0.8,
                )

        if objective_name == "high_upside_option":
            if left_thesis == "Peer benchmark marketplace":
                return _pairwise_payload(
                    winner="left",
                    summary=(
                        "The standalone benchmark marketplace remains the highest-upside bet because it "
                        "offers the strongest network-effect ceiling if trust can be earned."
                    ),
                    decisive_advantages=["Largest upside if benchmark sharing works."],
                    decisive_risks=["Trust and supply are still the gating risks."],
                    confidence=0.76,
                )
            if right_thesis == "Peer benchmark marketplace":
                return _pairwise_payload(
                    winner="right",
                    summary=(
                        "The standalone benchmark marketplace remains the highest-upside bet because it "
                        "offers the strongest network-effect ceiling if trust can be earned."
                    ),
                    decisive_advantages=["Largest upside if benchmark sharing works."],
                    decisive_risks=["Trust and supply are still the gating risks."],
                    confidence=0.76,
                )

        left_score = float(left_payload["score"]["total_score"])
        right_score = float(right_payload["score"]["total_score"])
        if left_score >= right_score:
            return _pairwise_payload(
                winner="left",
                summary="The left candidate wins on the stronger overall score-backed case.",
                decisive_advantages=["Better aggregate evaluation support."],
                decisive_risks=["The score gap may still narrow under real-world testing."],
                confidence=0.7,
            )
        return _pairwise_payload(
            winner="right",
            summary="The right candidate wins on the stronger overall score-backed case.",
            decisive_advantages=["Better aggregate evaluation support."],
            decisive_risks=["The score gap may still narrow under real-world testing."],
            confidence=0.7,
        )

    def _handle_stress_test(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> Critique:
        candidate = Candidate.from_dict(input_payload["candidate"])
        thesis = candidate.thesis
        return Critique(
            hidden_dependencies=[f"{thesis} depends on consistent operator follow-through."],
            kill_shots=[f"{thesis} fails if the retained artifacts do not change team behavior."],
            sharp_edges=[f"{thesis} could feel heavy during rollout without a narrow first use case."],
            summary=f"Stress-testing {thesis} surfaced adoption and behavior-change risk.",
        )

    def _handle_deepen(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> Candidate:
        candidate = Candidate.from_dict(input_payload["candidate"])
        thesis = candidate.thesis
        if "Workflow-native decision archive" in thesis:
            return Candidate(
                thesis="Workflow-native decision archive with instrumented rollout",
                mechanism=(
                    "Persist team decision branches, surface the strongest survivors in weekly rituals, "
                    "and instrument rollout milestones that prove the archive is changing behavior."
                ),
                assumptions=candidate.assumptions + ["Teams will adopt a ritual if the retained context saves recurring work."],
                strengths=candidate.strengths + ["Clear rollout instrumentation."],
                failure_modes=candidate.failure_modes,
                unknowns=["Which milestone best predicts retained usage across teams?"],
                implementation_shape="Start with one ritual, instrument retention, then expand the archive surface.",
                evidence=candidate.evidence,
            )
        if "Operational checklist assistant" in thesis:
            return Candidate(
                thesis="Operational checklist assistant with phased rollout",
                mechanism=(
                    "Embed an auditable checklist into one recurring team workflow first, then phase into adjacent workflows."
                ),
                assumptions=candidate.assumptions,
                strengths=candidate.strengths + ["Very controlled rollout."],
                failure_modes=candidate.failure_modes,
                unknowns=["Does the single-workflow wedge produce enough differentiation?"],
                implementation_shape="Ship to one workflow, capture behavior change, then broaden.",
                evidence=candidate.evidence,
            )
        return Candidate(
            thesis="Peer benchmark marketplace with trust bootstrap",
            mechanism=(
                "Start with private internal benchmarks, then graduate to trusted peer comparisons only after strong proof of value."
            ),
            assumptions=candidate.assumptions,
            strengths=candidate.strengths + ["Trust bootstrap path."],
            failure_modes=candidate.failure_modes,
            unknowns=["Can trusted cohorts be recruited fast enough?"], 
            implementation_shape="Begin private, then open carefully curated peer cohorts.",
            evidence=candidate.evidence,
        )

    def _handle_mutate(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> CandidateBatch:
        candidate = Candidate.from_dict(input_payload["candidate"])
        return CandidateBatch(
            candidates=[
                Candidate(
                    thesis="Workflow-native decision archive with lighter onboarding",
                    mechanism=(
                        "Keep the durable decision archive, but start with preloaded rituals and defaults so teams feel value before configuring much."
                    ),
                    assumptions=candidate.assumptions,
                    strengths=candidate.strengths + ["Reduces initial friction."],
                    failure_modes=candidate.failure_modes,
                    unknowns=["Do preloaded defaults generalize well enough across teams?"],
                    implementation_shape="Ship guided defaults, then open deeper configuration later.",
                    evidence=candidate.evidence,
                )
            ],
            batch_summary="Mutated the strongest archive bet to reduce onboarding risk.",
        )

    def _handle_combine(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> HybridCandidateBatch:
        return HybridCandidateBatch(
            decisions=[
                HybridCandidateDecision(
                    hybrid_name="Workflow-native archive with delayed peer benchmark layer",
                    seam_hypothesis=(
                        "The private workflow archive repairs the trust and cold-start weaknesses of the benchmark concept, "
                        "so the benchmark layer only activates after the archive already compounds value."
                    ),
                    repaired_failure_mode="Peer benchmarks fail when trust and proprietary-data value are not established first.",
                    complementary_strengths=[
                        "Workflow archive provides durable internal value and auditable artifacts.",
                        "Benchmarks add upside only after the product already owns the core ritual.",
                    ],
                    complexity_tax=(
                        "The product still has to sequence two modes and delay the benchmark layer until enough private value exists."
                    ),
                    expected_upside="Preserves the strongest moat while keeping a credible path to higher upside later.",
                    open_questions=["What trust threshold is high enough before any benchmark sharing turns on?"],
                    verdict=HybridVerdict.PURSUE,
                    summary="Pursue the hybrid because sequencing repairs the benchmark idea's weakest dependency without bloating the initial product.",
                    candidate=Candidate(
                        thesis="Workflow-native decision archive paired with peer benchmarks",
                        mechanism=(
                            "Use the archived workflow data as the base product, then layer in trusted peer benchmarks only once enough internal value is proven."
                        ),
                        assumptions=["Teams will share benchmark data once the private archive already delivers clear value."],
                        strengths=["Combines durable artifacts with network-style upside."],
                        failure_modes=["Could still become operationally heavy."],
                        unknowns=["What level of trust is required before benchmark sharing works?"],
                        implementation_shape="Private archive first, benchmark layer second.",
                        evidence=["Hybridizing the strongest moat with the boldest upside can preserve both if sequencing is disciplined."],
                    ),
                )
            ],
            batch_summary="Combined the most credible moat with the highest-upside extension.",
        )

    def _handle_migrate(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> Candidate:
        source_candidate = Candidate.from_dict(input_payload["source_candidate"])
        destination_island = dict(input_payload["destination_island"])
        destination_island_id = str(destination_island["island_id"])

        if destination_island_id == "upside":
            return Candidate(
                thesis="Workflow-native decision archive with benchmark calibration",
                mechanism=(
                    "Start from the retained workflow archive, then add selective peer benchmark "
                    "calibration only after the private archive proves recurring value."
                ),
                assumptions=source_candidate.assumptions
                + ["Teams will tolerate a benchmark layer once the private archive already pays off."],
                strengths=source_candidate.strengths + ["Carries a stronger upside narrative."],
                failure_modes=source_candidate.failure_modes + ["Could reintroduce trust complexity too early."],
                unknowns=["Which benchmark signal is valuable enough to justify the extra layer?"],
                implementation_shape="Private archive first, benchmark calibration second.",
                evidence=source_candidate.evidence,
            )

        if destination_island_id == "conservative":
            return Candidate(
                thesis="Operational checklist assistant backed by archived decision evidence",
                mechanism=(
                    "Use the source archive insight to ground an auditable checklist assistant "
                    "that can point back to prior decisions and rationale during rollout."
                ),
                assumptions=source_candidate.assumptions,
                strengths=source_candidate.strengths + ["Safer rollout with clearer justification."],
                failure_modes=source_candidate.failure_modes,
                unknowns=["How much archived context belongs in the checklist flow?"], 
                implementation_shape="Checklist wedge first, archived evidence inline as proof.",
                evidence=source_candidate.evidence,
            )

        return Candidate(
            thesis="Workflow-native decision archive with controlled rollout proof",
            mechanism=(
                "Carry the source insight into a balanced destination by preserving the archive "
                "moat while making the rollout proof and operating ritual more explicit."
            ),
            assumptions=source_candidate.assumptions,
            strengths=source_candidate.strengths + ["Better fit to a balanced island prior."],
            failure_modes=source_candidate.failure_modes,
            unknowns=["Which first ritual best proves the migrated idea in the destination island?"],
            implementation_shape="Single ritual rollout with explicit proof milestones.",
            evidence=source_candidate.evidence,
        )

    def _handle_compress_learning(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> LearningCompression:
        archived_nodes = list(input_payload["archived_nodes"])
        source_node_ids = [item["node_id"] for item in archived_nodes[:2]]
        return LearningCompression(
            notes=[
                LearningNote(
                    note_type=LearningNoteType.WINNING_PATTERN,
                    text="Workflow-native, auditable mechanisms outperform generic chat-shaped ideas.",
                    source_node_ids=source_node_ids,
                ),
                LearningNote(
                    note_type=LearningNoteType.FAILURE_PATTERN,
                    text="Ideas that do not create retained artifacts fail quickly, even if they sound easy to ship.",
                    source_node_ids=source_node_ids[:1],
                ),
            ],
            summary="Compressed the search into durable win and failure patterns.",
        )


def _workflow_archive_candidate() -> Candidate:
    return Candidate(
        thesis="Workflow-native decision archive",
        mechanism=(
            "Persist every serious solution branch, rank survivors in repeated team rituals, "
            "and make the retained artifact the reason teams keep coming back."
        ),
        assumptions=["Teams will reuse a system that compounds prior decisions into future speed."],
        strengths=["Creates durable retention through retained context."],
        failure_modes=["Could feel heavy during onboarding."],
        unknowns=["How quickly do teams perceive the retained-value loop?"],
        implementation_shape="Anchor the product in one weekly team ritual first.",
        evidence=["The brief emphasizes evaluator-first search and replayable artifacts."],
    )


def _operational_assistant_candidate() -> Candidate:
    return Candidate(
        thesis="Operational checklist assistant",
        mechanism=(
            "Turn the strongest decisions into auditable checklists that plug directly into recurring operator workflows."
        ),
        assumptions=["Operators prefer reliability and clarity when adopting a new workflow tool."],
        strengths=["Easy to explain and trial."],
        failure_modes=["May not create a large enough moat."],
        unknowns=["Can the checklist wedge feel meaningfully differentiated?"], 
        implementation_shape="Start in a single recurring workflow.",
        evidence=["The brief values actionability and auditability."],
    )


def _benchmark_market_candidate() -> Candidate:
    return Candidate(
        thesis="Peer benchmark marketplace",
        mechanism=(
            "Aggregate anonymized workflow outcomes so teams can benchmark their decisions against trusted peers."
        ),
        assumptions=["Teams will share enough data if the benchmark value is high."],
        strengths=["Very large upside if network effects emerge."],
        failure_modes=["Hard to bootstrap trust and supply."],
        unknowns=["What trust threshold is required before sharing works?"], 
        implementation_shape="Bootstrap with curated cohorts and narrow benchmark scopes.",
        evidence=["The brief allows bold bets as long as the tradeoffs are explicit."],
    )


def _chat_wrapper_candidate() -> Candidate:
    return Candidate(
        thesis="AI brainstorm chat wrapper",
        mechanism="Add a polished chat surface around one-shot ideation and call it a workflow solution.",
        assumptions=["Users mainly want a nicer chat UI."],
        strengths=["Fast to build."],
        failure_modes=["No durable retention moat."],
        unknowns=["Would users come back after the first novelty spike?"], 
        implementation_shape="Ship chat first and hope workflow value emerges later.",
        evidence=["This is the kind of style-first idea the specs reject."],
    )


def _fixture_technical_dossier_markdown(proposal_id: str) -> str:
    return (
        f"# Technical Dossier: {proposal_id}\n\n"
        "## Mechanism Translation\n"
        "The proposal converts a surviving research family into a concrete control loop: "
        "coverage state selects the next information-gathering action, while authoring "
        "actions produce typed artifacts that become the durable evidence base.\n\n"
        "## Mathematical Rule or Formula\n"
        "Let each cell have priority p = uncertainty + hard_gate_risk - evidence_strength. "
        "The scheduler spends the next unit of budget where p is high, unless a survivor "
        "already has enough evidence and needs adversarial review before final selection.\n\n"
        "## Nanochat Integration Points\n"
        "This fixture is not a nanochat experiment, but it preserves the same artifact shape "
        "expected from real nanochat runs: exact file targets, concrete hooks, and falsifiable "
        "measurement points belong in this section.\n\n"
        "## Minimal Implementation Sketch\n"
        "Read the typed proposal, identify the local runtime hook, implement the smallest "
        "delta behind a flag, and write the resulting metric trace into the run artifact "
        "directory so it can be compared against the baseline.\n\n"
        "## Ablation Design\n"
        "Compare baseline, minimal delta, and one strengthened variant. Stop if the metric "
        "does not improve or if artifact generation becomes too slow for the configured "
        "budget.\n\n"
        "## Expected Signals\n"
        "The expected signal is a clearer final decision with stronger reversal conditions, "
        "not merely a longer markdown report.\n\n"
        "## Failure Modes\n"
        "The main failure mode is prose expansion without additional mechanism. The dossier "
        "must carry formulas, hooks, and tests instead of elaborating the same proposition.\n\n"
        "## Prior-Art Collision\n"
        "The fixture has no external prior-art claim. Mark real source-dependent claims as "
        "verification_needed unless the provider can identify a concrete source.\n\n"
        "## Verification Needed\n"
        "Verify that the persisted technical file is present and that the summary links to it.\n"
    )


def _score_payload(
    *,
    hard_constraint_pass: bool,
    hard_constraint_reasons: list[str],
    distinctiveness: float,
    usefulness: float,
    specificity: float,
    plausibility: float,
    implementation_tractability: float,
    upside: float,
    adversarial_robustness: float,
    evidence_quality: float,
    total_score: float,
    confidence_estimate: float,
) -> dict[str, object]:
    return {
        "hard_constraint_pass": hard_constraint_pass,
        "hard_constraint_reasons": hard_constraint_reasons,
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
    }


def _pairwise_payload(
    *,
    winner: str,
    summary: str,
    decisive_advantages: list[str],
    decisive_risks: list[str],
    confidence: float,
) -> dict[str, object]:
    return {
        "winner": winner,
        "summary": summary,
        "decisive_advantages": decisive_advantages,
        "decisive_risks": decisive_risks,
        "confidence": confidence,
    }
