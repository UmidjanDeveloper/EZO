"""Bounded visible HTML text, using only Python's non-executing HTMLParser.

No browser, lxml/XML entities, JavaScript, style/layout inference or network.
This is plain body text extraction, not rendered-page or table/formula fidelity.
"""

from html.parser import HTMLParser

from ezo_api.knowledge.ingestion.normalize import normalize_text
from ezo_api.knowledge.parsers.base import ParsedDocument, ParseError, Section
from ezo_api.knowledge.parsers.text import decode_text

MAX_BYTES = 2_000_000
MAX_EVENTS = 40_000
MAX_DEPTH = 128
MAX_SECTIONS = 5000
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
SKIP = frozenset(
    "head script style template noscript iframe object svg canvas nav footer form".split()
)
BLOCK = frozenset("p div section article main li blockquote pre tr br hr h1 h2 h3 h4 h5 h6".split())
HEADINGS = frozenset("h1 h2 h3 h4 h5 h6".split())


class _BodyText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.parts: list[str] = []
        self.sections: list[Section] = []
        self.heading: str | None = None
        self.events = 0
        self.chars = 0
        self.title = ""

    def event(self) -> None:
        self.events += 1
        if self.events > MAX_EVENTS:
            raise ParseError("HTML complexity limit exceeded.", "resource_limit")

    def emit(self, *, heading: bool = False) -> None:
        value = normalize_text("".join(self.parts)).strip()
        self.parts.clear()
        if not value:
            return
        if heading:
            self.heading = value[:300]
        if len(self.sections) >= MAX_SECTIONS:
            raise ParseError("HTML section limit exceeded.", "resource_limit")
        self.sections.append(Section(value, heading=self.heading))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.event()
        # Frequent HTML optional closing tags must not appear to accumulate depth.
        if tag in ("p", "li", "tr", "td", "th") and self.stack and self.stack[-1] == tag:
            self.stack.pop()
        if tag == "body":
            self.parts.clear()  # discard non-body fragments preceding a real body
        if tag in BLOCK and not any(t in SKIP for t in self.stack):
            self.emit()
        if tag not in VOID:
            if len(self.stack) >= MAX_DEPTH:
                raise ParseError("HTML nesting limit exceeded.", "resource_limit")
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        self.event()
        if tag in BLOCK and not any(t in SKIP for t in self.stack):
            self.emit(heading=tag in HEADINGS)
        if tag in self.stack:
            offset = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[offset:]

    def handle_data(self, data: str) -> None:
        self.event()
        if "title" in self.stack and len(self.title) < 300:
            self.title += data[: 300 - len(self.title)]
        if any(t in SKIP for t in self.stack):
            return
        self.chars += len(data)
        if self.chars > MAX_BYTES:
            raise ParseError("HTML text limit exceeded.", "resource_limit")
        self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        self.event()

    def handle_decl(self, decl: str) -> None:
        self.event()  # HTMLParser does not fetch or expand a DTD

    def unknown_decl(self, data: str) -> None:
        self.event()

    def handle_pi(self, data: str) -> None:
        self.event()


def parse_html_text(data: bytes, filename: str) -> ParsedDocument:
    if len(data) > MAX_BYTES:
        raise ParseError("HTML input is limited to 2 MB.", "resource_limit")
    collector = _BodyText()
    try:
        collector.feed(decode_text(data))
        collector.close()
        collector.emit()
    except ParseError:
        raise
    except (ValueError, AssertionError) as exc:
        raise ParseError("Malformed HTML could not be read safely.") from exc
    if not collector.sections:
        raise ParseError("No readable body text was found in the HTML.")
    return ParsedDocument(
        collector.sections,
        title=collector.title.strip() or None,
        metadata={"extraction": "bounded-html-text/v1", "coverage": "body_text_only"},
    )
