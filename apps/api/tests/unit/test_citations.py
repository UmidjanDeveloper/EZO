from ezo_api.knowledge.retrieval.citations import format_sources_for_prompt, verify_citations
from ezo_api.knowledge.retrieval.sources import SourceRef, number_sources


def _sources() -> list[SourceRef]:
    return number_sources(
        [
            SourceRef(
                kind="file",
                title="Hisobot",
                excerpt="Sotuv 20% oshdi.",
                source_name="My files · h.pdf",
                page_start=3,
                page_end=3,
                revision_number=2,
                chunk_index=4,
            ),
            SourceRef(
                kind="web",
                title="Stat",
                excerpt="Inflyatsiya 9%.",
                source_name="official",
                url="https://stat.uz/x",
                date="2026-10-01",
                reliability=0.95,
                primary=True,
            ),
        ]
    )


def test_valid_citations_are_kept_and_collected() -> None:
    check = verify_citations("Sotuv oshdi [1]. Inflyatsiya 9% [2][1].", _sources())
    assert check.text == "Sotuv oshdi [1]. Inflyatsiya 9% [2][1]."
    assert [s.n for s in check.cited] == [1, 2]
    assert check.invalid_numbers == []


def test_invented_citations_are_removed() -> None:
    check = verify_citations("Fakt [3]. Boshqa [1, 7].", _sources())
    assert check.text == "Fakt. Boshqa [1]."
    assert check.invalid_numbers == [3, 7]
    assert [s.n for s in check.cited] == [1]


def test_without_sources_every_marker_is_invalid() -> None:
    check = verify_citations("Manba [1] bor deb aytdi.", [])
    assert "[1]" not in check.text
    assert check.invalid_numbers == [1]


def test_prompt_block_has_provenance_and_data_tags() -> None:
    block = format_sources_for_prompt(_sources())
    assert "[1] Hisobot" in block and "p. 3" in block and "revision 2" in block
    assert "https://stat.uz/x" in block and "(primary)" in block
    assert '<source n="2">' in block


def test_metadata_is_serialisable() -> None:
    meta = _sources()[0].to_metadata()
    assert meta["location"] == "p. 3, revision 2, chunk 5"
    assert meta["n"] == 1
