"""Recognise the short audio clips browsers record. The declared type is not trusted."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioKind:
    mime_type: str
    extension: str


def sniff_audio(data: bytes) -> AudioKind | None:
    """Detect WebM/Matroska, Ogg, WAV, MP3 and MP4/M4A from the first bytes."""
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return AudioKind("audio/webm", "webm")
    if data.startswith(b"OggS"):
        return AudioKind("audio/ogg", "ogg")
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return AudioKind("audio/wav", "wav")
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return AudioKind("audio/mpeg", "mp3")
    if data[4:8] == b"ftyp":
        return AudioKind("audio/mp4", "m4a")
    return None
