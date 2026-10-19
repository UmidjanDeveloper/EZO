"""Safe file download responses shared by the API routes."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Response


def file_response(data: bytes, filename: str, mime_type: str, *, inline: bool = False) -> Response:
    ascii_name = filename.encode("ascii", "ignore").decode() or "file"
    kind = "inline" if inline else "attachment"
    disposition = f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            # Downloads are never rendered as active content in the API's origin
            # (HTML/SVG cannot run here); only images are shown inline.
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )
