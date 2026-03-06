from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import time

from argus.errors import ArgusValidationError
from argus.models import ActionType, Candidate, Critique, LearningNote, LearningNoteType, ProblemSpec
from argus.providers import ProviderArtifacts, ProviderResponse
from argus.search.contracts import CandidateBatch, LearningCompression, ProblemFrame


class SearchFixtureProvider:
    def __init__(
        self,
        root_dir: Path,
        *,
        name: str = "fixture",
        fail_on_action: str | None = None,
        sleep_by_action: dict[str, float] | None = None,
        seed_candidates: list[Candidate] | None = None,
        seed_candidates_by_island: dict[str, list[Candidate]] | None = None,
    ) -> None:
        self.root_dir = root_dir
        self.name = name
        self.fail_on_action = fail_on_action
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

            if self.fail_on_action == normalized_action:
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

    def _handle_assess_novelty(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        candidate_thesis = str(input_payload["candidate"]["thesis"])
        archive_candidates = list(input_payload["archive_candidates"])
        for archived in archive_candidates:
            archived_thesis = str(archived["candidate"]["thesis"])
            if archived_thesis == candidate_thesis:
                return {
                    "novelty_score": 0.12,
                    "max_similarity": 0.91,
                    "nearest_neighbor_id": archived["node_id"],
                    "similarity_threshold": input_payload["similarity_threshold"],
                    "is_novel": False,
                    "summary": "This is a near-duplicate of an archived candidate.",
                    "duplicate_signals": ["Same thesis.", "Same mechanism family."],
                }

        if "chat wrapper" in candidate_thesis.lower():
            return {
                "novelty_score": 0.68,
                "max_similarity": 0.31,
                "nearest_neighbor_id": None,
                "similarity_threshold": input_payload["similarity_threshold"],
                "is_novel": True,
                "summary": "The idea is distinct, but it may still fail on quality.",
                "duplicate_signals": [],
            }

        return {
            "novelty_score": 0.86,
            "max_similarity": 0.22,
            "nearest_neighbor_id": None,
            "similarity_threshold": input_payload["similarity_threshold"],
            "is_novel": True,
            "summary": "The candidate is meaningfully distinct from the archive.",
            "duplicate_signals": [],
        }

    def _handle_evaluate_candidate(
        self,
        _: ProblemSpec,
        input_payload: dict[str, object],
    ) -> dict[str, object]:
        candidate = Candidate.from_dict(input_payload["candidate"])
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
    ) -> CandidateBatch:
        return CandidateBatch(
            candidates=[
                Candidate(
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
                )
            ],
            batch_summary="Combined the most credible moat with the highest-upside extension.",
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
