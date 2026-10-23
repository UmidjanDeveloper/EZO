"""Pure Python web reading never invokes the native XML/HTML extraction engine."""

import pytest

from ezo_api.knowledge.parsers.base import ParseError
from ezo_api.knowledge.parsers.html_text import parse_html_text


def test_visible_text_unicode_headings_and_inline_content_without_execution():
    data = (
        "<html><head><title>O‘zbekiston 🙂</title><script>secret()</script></head>"
        "<body><nav>menu</nav><h1>Bilim</h1><p>py<span>thon</span> &amp; dalil.</p>"
        "<script>fetch('https://example.org')</script><style>invisible</style>"
        "<iframe src='file:///etc/passwd'>secret</iframe><p>Ikkinchi bo‘lim.</p></body></html>"
    ).encode()
    parsed = parse_html_text(data, "page.html")
    assert parsed.title == "O‘zbekiston 🙂"
    assert parsed.sections[0].heading == "Bilim"
    assert "python & dalil." in parsed.text
    assert "Ikkinchi bo‘lim." in parsed.text
    assert all(s not in parsed.text for s in ("secret", "menu", "fetch(", "invisible"))
    assert parsed.metadata == {"extraction": "bounded-html-text/v1", "coverage": "body_text_only"}


@pytest.mark.parametrize(
    "payload",
    [
        b"x" * 2_000_001,
        b"<div>" * 129 + b"text" + b"</div>" * 129,
        b"<p>x</p>" * 5001,
        b"<!--x-->" * 40_001,
    ],
)
def test_resource_boundaries_return_structured_error(payload):
    with pytest.raises(ParseError) as exc:
        parse_html_text(payload, "malformed.html")
    assert exc.value.code == "resource_limit"


def test_dtd_does_not_resolve_external_entities():
    parsed = parse_html_text(
        b'<!DOCTYPE html SYSTEM "file:///etc/passwd"><p>Evidence &unknown;</p>', "page.html"
    )
    assert "Evidence" in parsed.text
    assert "root:" not in parsed.text


def test_ordinary_optional_paragraph_close_and_html_fragment():
    parsed = parse_html_text(b"<p>First<p>Second<p>Third", "fragment.html")
    assert [s.text for s in parsed.sections] == ["First", "Second", "Third"]


def test_production_html_dispatch_never_calls_trafilatura(monkeypatch):
    from ezo_api.knowledge.parsers import html

    monkeypatch.setattr(html, "native_fixtures_allowed", lambda: False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Native HTML parser must not receive this input")

    monkeypatch.setattr(html.trafilatura, "extract", forbidden)
    assert (
        html.parse_html(b"<p>Authorized body text.</p>", "page.html").text
        == "Authorized body text."
    )
