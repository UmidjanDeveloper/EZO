"""Splitting long documents at their own sections, without losing text."""

from __future__ import annotations

import pytest

from ezo_api.documents.longdoc import TooLongError, is_heading, outline, split_parts


@pytest.mark.parametrize(
    "line",
    [
        "# Kirish",
        "1.2. Umumiy qoidalar",
        "5-modda. Huquqlar",
        "II BOB. YAKUNIY QOIDALAR",
        "Статья 12. Ответственность",
        "Глава 3",
        "Article 4 Scope",
        "UMUMIY QOIDALAR",
    ],
)
def test_headings_in_three_languages(line: str) -> None:
    assert is_heading(line)


@pytest.mark.parametrize("line", ["Bu oddiy gap, sarlavha emas.", "2026-yil 1-yanvar", ""])
def test_ordinary_lines_are_not_headings(line: str) -> None:
    assert not is_heading(line)


def law(articles: int, words: int) -> str:
    return "\n\n".join(
        f"{n}-modda. Modda {n} nomi\n" + " ".join(f"m{n}s{i}" for i in range(words))
        for n in range(1, articles + 1)
    )


def test_parts_follow_sections_and_keep_every_word() -> None:
    text = law(8, 600)
    parts = split_parts(text, limit=9_000)
    assert len(parts) > 1 and all(len(p.text) <= 9_000 for p in parts)
    joined = " ".join(p.text for p in parts)
    assert all(f"m{n}s599" in joined for n in range(1, 9))  # nothing dropped
    assert parts[0].titles[0] == "1-modda. Modda 1 nomi"
    assert all(p.text.lstrip().split("\n")[0].endswith("nomi") for p in parts)  # cut at headings
    assert outline(text)[:2] == ["1-modda. Modda 1 nomi", "2-modda. Modda 2 nomi"]


def test_a_huge_section_is_cut_at_paragraphs() -> None:
    body = "\n\n".join("Gap. " * 200 for _ in range(30))
    parts = split_parts("1-modda. Katta modda\n" + body, limit=5_000)
    assert len(parts) > 3 and all(len(p.text) <= 5_000 for p in parts)
    assert all(p.titles == ("1-modda. Katta modda",) for p in parts)


def test_over_the_limit_is_refused_not_cut() -> None:
    with pytest.raises(TooLongError):
        split_parts("x" * 2_000_001)
