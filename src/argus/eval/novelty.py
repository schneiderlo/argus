from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import difflib
import math
import re

from argus.errors import ArgusValidationError
from argus.models import Candidate, Node

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
    "thesis",
    "mechanism",
    "assumptions",
    "strengths",
    "failure",
    "modes",
    "unknowns",
    "evidence",
    "implementation",
    "shape",
}


@dataclass(frozen=True, slots=True)
class NoveltyConfig:
    similarity_threshold: float = 0.79

    def __post_init__(self) -> None:
        value = self.similarity_threshold
        if not isinstance(value, int | float) or not math.isfinite(value):
            raise ArgusValidationError(
                "similarity_threshold must be a finite number, "
                f"got {value!r}."
            )
        if value < 0 or value > 1:
            raise ArgusValidationError(
                "similarity_threshold must be between 0 and 1 inclusive, "
                f"got {value!r}."
            )


@dataclass(frozen=True, slots=True)
class NoveltyAssessment:
    novelty_score: float
    max_similarity: float
    nearest_neighbor_id: str | None
    similarity_threshold: float
    is_novel: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "novelty_score",
            _normalize_probability(self.novelty_score, "novelty_score"),
        )
        object.__setattr__(
            self,
            "max_similarity",
            _normalize_probability(self.max_similarity, "max_similarity"),
        )
        object.__setattr__(
            self,
            "similarity_threshold",
            _normalize_probability(self.similarity_threshold, "similarity_threshold"),
        )
        if self.nearest_neighbor_id is not None:
            if not isinstance(self.nearest_neighbor_id, str) or not self.nearest_neighbor_id.strip():
                raise ArgusValidationError(
                    "nearest_neighbor_id must be a non-empty string or None."
                )
            object.__setattr__(self, "nearest_neighbor_id", self.nearest_neighbor_id.strip())
        if not isinstance(self.is_novel, bool):
            raise ArgusValidationError(
                f"is_novel must be a boolean, got {type(self.is_novel).__name__}."
            )


class TextNoveltyFilter:
    """Measure candidate novelty from stable text projections."""

    def __init__(self, *, config: NoveltyConfig = NoveltyConfig()) -> None:
        self._config = config

    @property
    def config(self) -> NoveltyConfig:
        return self._config

    def compare(self, left: Candidate, right: Candidate) -> float:
        left_projection = _projection_text(left)
        right_projection = _projection_text(right)

        left_token_list = _content_token_list(left_projection)
        right_token_list = _content_token_list(right_projection)
        left_tokens = set(left_token_list)
        right_tokens = set(right_token_list)
        token_similarity = _overlap_similarity(left_tokens, right_tokens)

        left_bigrams = _ngrams(left_token_list, 2)
        right_bigrams = _ngrams(right_token_list, 2)
        bigram_similarity = _overlap_similarity(left_bigrams, right_bigrams)

        sequence_similarity = difflib.SequenceMatcher(
            a=_normalize_space(left_projection),
            b=_normalize_space(right_projection),
            autojunk=False,
        ).ratio()

        return round(
            _clamp(
                0.70 * token_similarity
                + 0.10 * bigram_similarity
                + 0.20 * sequence_similarity
            ),
            4,
        )

    def assess(self, candidate: Candidate, archive_nodes: Iterable[Node]) -> NoveltyAssessment:
        nearest_neighbor_id: str | None = None
        max_similarity = 0.0

        for node in sorted(archive_nodes, key=lambda item: item.node_id):
            similarity = self.compare(candidate, node.candidate)
            if similarity > max_similarity:
                max_similarity = similarity
                nearest_neighbor_id = node.node_id

        novelty_score = round(1.0 - max_similarity, 4)
        is_novel = max_similarity < self._config.similarity_threshold
        return NoveltyAssessment(
            novelty_score=novelty_score,
            max_similarity=max_similarity,
            nearest_neighbor_id=nearest_neighbor_id,
            similarity_threshold=self._config.similarity_threshold,
            is_novel=is_novel,
        )


def _projection_text(candidate: Candidate) -> str:
    return candidate.text_projection()


def _content_tokens(text: str) -> set[str]:
    return set(_content_token_list(text))


def _content_token_list(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    ]


def _normalize_space(text: str) -> str:
    return " ".join(text.lower().split())


def _ngrams(tokens: list[str], size: int) -> set[tuple[str, ...]]:
    if size <= 0:
        raise ArgusValidationError("ngram size must be positive.")
    if len(tokens) < size:
        return set()
    return {tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def _overlap_similarity(left: set[object], right: set[object]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return min(max(value, lower), upper)


def _normalize_probability(value: float, field_name: str) -> float:
    if not isinstance(value, int | float) or not math.isfinite(value):
        raise ArgusValidationError(
            f"{field_name} must be a finite number, got {value!r}."
        )
    if value < 0 or value > 1:
        raise ArgusValidationError(
            f"{field_name} must be between 0 and 1 inclusive, got {value!r}."
        )
    return float(value)
