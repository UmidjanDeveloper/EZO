"""Memory relevance scoring (lexical, Milestone 1).

Retrieval score = relevance (word overlap with the query) + importance +
recency. Semantic (embedding) retrieval replaces the relevance part in
Milestone 2 through the VectorStore interface; the combination stays the same.
"""

from __future__ import annotations

import math
from datetime import datetime

from ezo_api.core.text import tokenize

_STOPWORDS = set(
    """
    the a an and or is are to of in on for it i you me my we be that this with what how do
    can va bu u men sen siz biz uchun bilan ham edi nima qanday menga mening ezo и в на я
    ты вы мы что как это не с для мне
    """.split()
)

STEM_LENGTH = 5
"""Comparing word prefixes approximates stemming for Uzbek/Russian suffixes."""

WEIGHT_RELEVANCE = 0.6
WEIGHT_IMPORTANCE = 0.25
WEIGHT_RECENCY = 0.15
RECENCY_HALF_LIFE_DAYS = 30.0


def stem_tokens(text: str) -> list[str]:
    """Word stems in order (with repeats), stopwords removed."""
    return [
        token[:STEM_LENGTH]
        for token in tokenize(text)
        if token not in _STOPWORDS and (len(token) > 2 or token.isdigit())
    ]


def stems(text: str) -> set[str]:
    return set(stem_tokens(text))


def relevance(query_stems: set[str], memory_text: str) -> float:
    memory_stems = stems(memory_text)
    if not query_stems or not memory_stems:
        return 0.0
    overlap = len(query_stems & memory_stems)
    return overlap / math.sqrt(len(query_stems) * len(memory_stems))


def recency(updated_at: datetime, now: datetime) -> float:
    age_days = max((now - updated_at).total_seconds() / 86_400, 0.0)
    return math.pow(0.5, age_days / RECENCY_HALF_LIFE_DAYS)


def combined_score(rel: float, importance: float, updated_at: datetime, now: datetime) -> float:
    return (
        WEIGHT_RELEVANCE * rel
        + WEIGHT_IMPORTANCE * importance
        + WEIGHT_RECENCY * recency(updated_at, now)
    )


# Hybrid weights when a semantic (embedding) score is available.
H_SEMANTIC = 0.45
H_LEXICAL = 0.15
H_IMPORTANCE = 0.2
H_RECENCY = 0.1
H_PROJECT = 0.1


def hybrid_score(
    semantic: float,
    lexical: float,
    importance: float,
    updated_at: datetime,
    now: datetime,
    project_match: bool,
) -> float:
    return (
        H_SEMANTIC * max(semantic, 0.0)
        + H_LEXICAL * lexical
        + H_IMPORTANCE * importance
        + H_RECENCY * recency(updated_at, now)
        + H_PROJECT * (1.0 if project_match else 0.0)
    )
