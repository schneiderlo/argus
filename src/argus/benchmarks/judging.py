from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from argus.benchmarks.models import (
    BenchmarkCase,
    BenchmarkComparisonAssessment,
    BenchmarkRuntimeMode,
)
from argus.errors import ArgusValidationError
from argus.models import FinalRecommendation, JSONValue
from argus.providers import Provider, StructuredOutputSchema


@dataclass(frozen=True, slots=True)
class BenchmarkModeSubmission:
    runtime_mode: BenchmarkRuntimeMode
    summary_markdown: str
    final_recommendation: FinalRecommendation
    best_bet_thesis: str
    conservative_thesis: str | None = None
    high_upside_thesis: str | None = None
    research_final_decision: dict[str, JSONValue] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_mode, BenchmarkRuntimeMode):
            object.__setattr__(
                self,
                "runtime_mode",
                BenchmarkRuntimeMode(str(self.runtime_mode).strip()),
            )
        object.__setattr__(
            self,
            "summary_markdown",
            _normalize_non_empty_string(self.summary_markdown, "summary_markdown"),
        )
        if not isinstance(self.final_recommendation, FinalRecommendation):
            raise ArgusValidationError(
                "final_recommendation must be a FinalRecommendation instance."
            )
        object.__setattr__(
            self,
            "best_bet_thesis",
            _normalize_non_empty_string(self.best_bet_thesis, "best_bet_thesis"),
        )
        object.__setattr__(
            self,
            "conservative_thesis",
            _normalize_optional_string(self.conservative_thesis, "conservative_thesis"),
        )
        object.__setattr__(
            self,
            "high_upside_thesis",
            _normalize_optional_string(self.high_upside_thesis, "high_upside_thesis"),
        )
        if self.research_final_decision is not None and not isinstance(
            self.research_final_decision, dict
        ):
            raise ArgusValidationError(
                "research_final_decision must be a dict or None."
            )

    def to_prompt_dict(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "runtime_mode": self.runtime_mode.value,
            "summary_markdown": self.summary_markdown,
            "final_recommendation": self.final_recommendation.to_dict(),
            "selected_theses": {
                "best_bet": self.best_bet_thesis,
                "conservative": self.conservative_thesis,
                "high_upside": self.high_upside_thesis,
            },
        }
        if self.research_final_decision is not None:
            payload["research_final_decision"] = self.research_final_decision
        return payload


class BenchmarkComparisonJudge:
    def __init__(self, *, provider: Provider) -> None:
        self._provider = provider

    def compare(
        self,
        *,
        case: BenchmarkCase,
        submissions: Iterable[BenchmarkModeSubmission],
    ) -> BenchmarkComparisonAssessment:
        if not isinstance(case, BenchmarkCase):
            raise ArgusValidationError(
                f"case must be a BenchmarkCase instance, got {type(case).__name__}."
            )
        normalized_submissions = _normalize_submissions(submissions)
        if len(normalized_submissions) < 2:
            raise ArgusValidationError(
                "Benchmark comparison judge requires at least two runtime submissions."
            )

        response = self._provider.run_action(
            action_name="judge_benchmark_modes",
            problem_spec=case.problem_spec,
            input_payload={
                "benchmark_case": {
                    "case_id": case.case_id,
                    "title": case.title,
                    "family": case.family.value,
                    "budget": case.budget,
                    "evaluation_notes": list(case.evaluation_notes),
                    "expected_qualities": list(case.expected_qualities),
                    "tags": list(case.tags),
                },
                "judging_rubric": {
                    "primary_goal": (
                        "Choose the runtime output a serious team should act on next."
                    ),
                    "dimensions": [
                        "decision_quality",
                        "actionability",
                        "tradeoff_clarity",
                        "risk_quality",
                        "experiment_quality",
                    ],
                    "winner_rule": (
                        "Prefer the option with the strongest decision quality and actionability, "
                        "not the prettiest prose."
                    ),
                    "adversarial_checks": [
                        "Generic polished summaries without concrete tradeoffs should lose.",
                        "A strong first spike must be specific and discriminating.",
                        "Risk and reversal-condition handling must be decision-grade.",
                    ],
                },
                "mode_outputs": [
                    submission.to_prompt_dict() for submission in normalized_submissions
                ],
            },
            output_schema=benchmark_comparison_assessment_schema(),
        )
        return response.payload


def benchmark_comparison_assessment_schema() -> StructuredOutputSchema[BenchmarkComparisonAssessment]:
    runtime_mode_enum = [mode.value for mode in BenchmarkRuntimeMode]
    mode_judgment_schema: dict[str, JSONValue] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "runtime_mode",
            "decision_quality",
            "actionability",
            "tradeoff_clarity",
            "risk_quality",
            "experiment_quality",
            "overall_score",
            "strengths",
            "weaknesses",
            "evidence",
        ],
        "properties": {
            "runtime_mode": {"type": "string", "enum": runtime_mode_enum},
            "decision_quality": {"type": "number", "minimum": 0, "maximum": 1},
            "actionability": {"type": "number", "minimum": 0, "maximum": 1},
            "tradeoff_clarity": {"type": "number", "minimum": 0, "maximum": 1},
            "risk_quality": {"type": "number", "minimum": 0, "maximum": 1},
            "experiment_quality": {"type": "number", "minimum": 0, "maximum": 1},
            "overall_score": {"type": "number", "minimum": 0, "maximum": 1},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
    }
    return StructuredOutputSchema(
        name="benchmark_comparison_assessment",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "winner_runtime_mode",
                "runner_up_runtime_mode",
                "summary",
                "confidence",
                "decisive_reasons",
                "watchouts",
                "mode_judgments",
            ],
            "properties": {
                "winner_runtime_mode": {"type": "string", "enum": runtime_mode_enum},
                "runner_up_runtime_mode": {"type": "string", "enum": runtime_mode_enum},
                "summary": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "decisive_reasons": {"type": "array", "items": {"type": "string"}},
                "watchouts": {"type": "array", "items": {"type": "string"}},
                "mode_judgments": {
                    "type": "array",
                    "minItems": 2,
                    "items": mode_judgment_schema,
                },
            },
        },
        validator=BenchmarkComparisonAssessment.from_dict,
    )


def _normalize_submissions(
    submissions: Iterable[BenchmarkModeSubmission],
) -> list[BenchmarkModeSubmission]:
    normalized = list(submissions)
    if not normalized:
        return []
    seen: set[BenchmarkRuntimeMode] = set()
    for index, submission in enumerate(normalized):
        if not isinstance(submission, BenchmarkModeSubmission):
            raise ArgusValidationError(
                f"submissions[{index}] must be a BenchmarkModeSubmission, "
                f"got {type(submission).__name__}."
            )
        if submission.runtime_mode in seen:
            raise ArgusValidationError(
                f"submissions contains duplicate runtime_mode values: {submission.runtime_mode.value}."
            )
        seen.add(submission.runtime_mode)
    return normalized


def _normalize_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized


def _normalize_optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_non_empty_string(value, field_name)
