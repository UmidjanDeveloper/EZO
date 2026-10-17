from ezo_api.knowledge.ingestion.chunking import MAX_CHARS, chunk_sections
from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers.base import Section


def test_normalize_text() -> None:
    assert (
        normalize_text("Hello   world\r\n\r\n\r\n\r\nnext-\nline\x07") == "Hello world\n\nnextline"
    )
    assert normalize_text("Toshkent-\nSamarqand") == "Toshkent-\nSamarqand"  # proper noun kept


def test_chunks_respect_size_pages_and_overlap() -> None:
    paragraph = "Bu jumla bilim bazasi uchun sinov matni hisoblanadi. " * 12
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


def test_very_long_sentence_is_split() -> None:
    chunks = chunk_sections([Section(text="so‘z " * 2000)])
    assert all(len(c.text) <= MAX_CHARS for c in chunks)
    assert len(chunks) > 3


def test_empty_sections_give_no_chunks() -> None:
    assert chunk_sections([Section(text="   \n\n ")]) == []
