import pytest

from ezo_api.knowledge.ingestion.chunking import MAX_CHARS, chunk_sections
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers.base import Section


def test_normalize_text() -> None:
    assert (
        normalize_text("Hello   world\r\n\r\n\r\n\r\nnext-\nline\x07") == "Hello world\n\nnextline"
    )
    assert normalize_text("Toshkent-\nSamarqand") == "Toshkent-\nSamarqand"  # proper noun kept


def test_chunks_respect_size_pages_and_overlap() -> None:
    # Multiple chunks per page exercise retained overlap within a location as well
    # as the transition where carrying the previous page's text would miscite it.
    paragraph = "Bu jumla bilim bazasi uchun sinov matni hisoblanadi. " * 48
    sections = [
        Section(text=paragraph, page=1),
        Section(text=paragraph, page=2, heading="Ikkinchi"),
    ]
    chunks = chunk_sections(sections)
    assert len(chunks) >= 2
    assert all(0 < len(c.text) <= MAX_CHARS for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].metadata["page_start"] == 1
    assert chunks[-1].metadata["page_end"] == 2
    assert chunks[-1].metadata.get("overlap") is True
    first_on_page_two = next(c for c in chunks if c.metadata["page_start"] == 2)
    assert not first_on_page_two.metadata.get("overlap")


def test_very_long_sentence_is_split() -> None:
    chunks = chunk_sections([Section(text="so‘z " * 2000)])
    assert all(len(c.text) <= MAX_CHARS for c in chunks)
    assert len(chunks) > 3


def test_empty_sections_give_no_chunks() -> None:
    assert chunk_sections([Section(text="   \n\n ")]) == []


@pytest.mark.parametrize("boundary", ["page", "heading"])
def test_citation_location_never_labels_text_from_another_location(boundary: str) -> None:
    first = Section(text="FIRST_LOCATION_ONLY: birinchi bob dalili.", page=1, heading="Birinchi")
    second = Section(
        text="SECOND_LOCATION_ONLY: ikkinchi bob dalili.",
        page=2 if boundary == "page" else 1,
        heading="Ikkinchi" if boundary == "heading" else "Birinchi",
    )
    chunks = chunk_sections([first, second])
    assert len(chunks) == 2
    assert "SECOND_LOCATION_ONLY" not in chunks[0].text
    assert "FIRST_LOCATION_ONLY" not in chunks[1].text
    assert chunks[0].metadata["page_start"] == chunks[0].metadata["page_end"] == 1
    assert chunks[1].metadata["page_start"] == chunks[1].metadata["page_end"] == second.page
    assert chunks[0].metadata["heading"] == first.heading
    assert chunks[1].metadata["heading"] == second.heading
