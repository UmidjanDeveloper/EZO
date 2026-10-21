"""Bounded EPUB spine reader, used only inside an isolated workload.

Reads ZIP members in memory, never extracts paths, follows network references or
executes book scripts. Access/copyright permission is the uploader's responsibility.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import fromstring

from ezo_api.knowledge.parsers.base import ParsedDocument, ParseError, Section

XML_BYTES = 2 * 1024 * 1024
TOTAL_BYTES = 128 * 1024 * 1024


def resolve(base: str, ref: str) -> str:
    url = urlsplit(ref)
    decoded = unquote(url.path)
    if url.scheme or url.netloc or url.query or "\\" in decoded or "%" in decoded:
        raise ParseError("Unsafe EPUB member reference.")
    if decoded.startswith("/") or not decoded or len(decoded) > 400:
        raise ParseError("Unsafe EPUB member reference.")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), decoded))
    if path == ".." or path.startswith("../"):
        raise ParseError("EPUB member reference leaves its archive.")
    return path


def _xml(archive: zipfile.ZipFile, name: str) -> Element:
    info = archive.getinfo(name)
    if info.file_size > XML_BYTES:
        raise ParseError("EPUB XML exceeds its expanded-size budget.")
    with archive.open(info) as source:
        data = source.read(XML_BYTES + 1)
    if len(data) > XML_BYTES:
        raise ParseError("EPUB XML exceeds its expanded-size budget.")
    return fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def parse_epub(data: bytes) -> ParsedDocument:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 5000 or sum(i.file_size for i in infos) > TOTAL_BYTES:
                raise ParseError("EPUB expansion exceeds its budget.")
            names = set()
            for info in infos:
                name = info.filename
                if (
                    name.startswith("/")
                    or "\\" in name
                    or ".." in name.split("/")
                    or name in names
                    or info.flag_bits & 1
                ):
                    raise ParseError("Unsafe or ambiguous EPUB archive members.")
                names.add(name)
            mimetype = archive.getinfo("mimetype")
            if mimetype.file_size != len(b"application/epub+zip"):
                raise ParseError("Not a supported EPUB archive.")
            if archive.read(mimetype) != b"application/epub+zip":
                raise ParseError("Not an EPUB archive.")
            container = _xml(archive, "META-INF/container.xml")
            roots = [e for e in container.iter() if e.tag.rsplit("}", 1)[-1] == "rootfile"]
            if len(roots) != 1:
                raise ParseError("EPUB must have one supported root document.")
            package = resolve("", roots[0].get("full-path", ""))
            root = _xml(archive, package)
            manifest = {}
            spine = []
            for node in root.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                if tag == "item":
                    identifier = node.get("id", "")
                    if not identifier or identifier in manifest:
                        raise ParseError("Ambiguous EPUB manifest.")
                    manifest[identifier] = (node.get("href", ""), node.get("media-type", ""))
                elif tag == "itemref":
                    spine.append(node.get("idref", ""))
            if not spine or len(spine) > 1000 or len(manifest) > 2000:
                raise ParseError("EPUB spine exceeds its complexity budget.")
            sections = []
            members = []
            chars = 0
            for identifier in spine:
                href, media = manifest[identifier]
                if media not in ("application/xhtml+xml", "text/html"):
                    raise ParseError("Unsupported EPUB spine content.")
                member = resolve(package, href)
                chapter = _xml(archive, member)
                # Scripts/styles are not reading content and are never executed.
                for parent in chapter.iter():
                    for child in list(parent):
                        if child.tag.rsplit("}", 1)[-1].lower() in ("script", "style"):
                            parent.remove(child)
                bodies = [e for e in chapter.iter() if e.tag.rsplit("}", 1)[-1] == "body"]
                if len(bodies) != 1:
                    raise ParseError("EPUB chapter has no unique reading body.")
                text = " ".join(bodies[0].itertext())
                chars += len(text)
                if chars > 2_000_000:
                    raise ParseError("EPUB text exceeds its character budget.")
                heading_node = next(
                    (
                        node
                        for node in bodies[0].iter()
                        if node.tag.rsplit("}", 1)[-1].lower()
                        in ("h1", "h2", "h3", "h4", "h5", "h6")
                    ),
                    None,
                )
                heading = (
                    " ".join(" ".join(heading_node.itertext()).split())[:200]
                    if heading_node is not None
                    else None
                )
                sections.append(Section(text=text, heading=heading or None))
                members.append(member)
            return ParsedDocument(sections=sections, metadata={"section_sources": members})
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("The EPUB is malformed or unsupported.") from exc
