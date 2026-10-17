from datetime import timedelta

from ezo_api.db.base import utcnow
from ezo_api.memory.scoring import combined_score, recency, relevance, stems


def test_stems_handle_uzbek_suffixes() -> None:
    assert relevance(stems("dizayn haqida gaplashamiz"), "men minimalist dizaynni yoqtiraman") > 0


def test_unrelated_text_has_zero_relevance() -> None:
    assert relevance(stems("weather tomorrow"), "men minimalist dizaynni yoqtiraman") == 0


def test_recency_halves_after_half_life() -> None:
    now = utcnow()
    assert abs(recency(now - timedelta(days=30), now) - 0.5) < 1e-6


def test_combined_score_prefers_relevant_important_recent() -> None:
    now = utcnow()
    fresh = combined_score(0.8, 0.9, now, now)
    stale = combined_score(0.8, 0.9, now - timedelta(days=365), now)
    unimportant = combined_score(0.8, 0.1, now, now)
    assert fresh > stale
    assert fresh > unimportant
