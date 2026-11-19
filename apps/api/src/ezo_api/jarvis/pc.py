"""Computer actions EZO may ask a paired computer to do — each one only after the owner
approves that exact action.

The list is fixed: open an allowed app, list an allowed folder, open a file in an allowed
folder, open an https address. The words are read without a model; anything else is not a
computer action. Paths never travel: folders are aliases the computer maps itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from ezo_api.core.text import normalize

PC_ACTIONS = ("pc.open_app", "pc.list_folder", "pc.open_file", "pc.open_url")
FOLDERS = ("downloads", "documents", "desktop")
APPS = ("calculator", "notepad", "paint", "explorer", "word", "excel", "powerpoint")
BLOCKED_EXTENSIONS = frozenset(
    (
        "exe bat cmd com ps1 psm1 vbs vbe js jse wsf wsh msi msp lnk scr pif reg hta cpl jar app sh"
    ).split()
)

APP_WORDS: tuple[tuple[str, str], ...] = (
    ("calculator", r"kalkulyator|calculator|калькулятор"),
    ("notepad", r"notepad|bloknot|блокнот"),
    ("paint", r"\bpaint\b|пейнт"),
    ("explorer", r"explorer|provodnik|проводник|fayl menejer"),
    ("word", r"\bword(ni|ga|da)?\b|ворд"),
    ("excel", r"excel|эксель"),
    ("powerpoint", r"powerpoint|пауэрпоинт"),
)
FOLDER_WORDS: tuple[tuple[str, str], ...] = (
    ("downloads", r"yuklama|yuklab olingan|downloads?\b|загрузк"),
    ("documents", r"hujjatlar papka|mening hujjatlar|documents\b|документы"),
    ("desktop", r"ish stoli|desktop|рабоч\w* стол"),
)
_OPEN = r"(och|ishga tushir|yoq\b|open|launch|start|откр|запуст)"
_LIST = (
    r"(nima bor|nimalar bor|ro'yxat|ko'rsat|fayllar\w*|list|show|what is in|что в|покажи|список)"
)
_PC = r"(kompyuter|noutbuk|computer|laptop|компьютер|ноутбук)"
# A file name: in quotes (spaces allowed) or one word ("hisobot.docx", "2026_reja.xlsx").
_QUOTED_FILE = re.compile(r"[«\"“']([^«»\"“”']{1,120}\.[a-z0-9]{1,6})[»\"”']", re.IGNORECASE)
_FILE = re.compile(r"(?<![\w.])([\w()\-]+(?:\.[\w()\-]+)*\.[a-z0-9]{1,6})(?![\w.])", re.IGNORECASE)
_URL = re.compile(r"https://[^\s<>\"'`]+", re.IGNORECASE)

FOLDER_NAMES = {"downloads": "Yuklamalar", "documents": "Hujjatlar", "desktop": "Ish stoli"}
APP_NAMES = {
    "calculator": "Kalkulyator", "notepad": "Bloknot", "paint": "Paint", "explorer": "Provodnik",
    "word": "Word", "excel": "Excel", "powerpoint": "PowerPoint",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class PcCommand:
    action: str
    root: str
    target: str | None
    description: str
    """Uzbek, for the approval dialog: exactly what will happen."""

    def params(self) -> dict[str, str | None]:
        return {"root": self.root, "target": self.target}


def _folder(norm: str) -> str | None:
    for key, words in FOLDER_WORDS:
        if re.search(words, norm):
            return key
    return None


def safe_file_name(name: str) -> bool:
    name = name.strip()
    if not name or len(name) > 200 or name.startswith(".") or "/" in name or "\\" in name:
        return False
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return bool(extension) and extension not in BLOCKED_EXTENSIONS


def safe_url(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.scheme == "https" and bool(parts.hostname) and not parts.username and len(url) <= 500
    )


def parse_pc_command(text: str) -> PcCommand | None:
    """A computer action named in the message, or None."""
    norm = normalize(text)
    has_open = re.search(_OPEN, norm)
    url = _URL.search(text)
    if url and has_open:
        address = url.group(0).rstrip(".,;:!?)»")
        if safe_url(address):
            return PcCommand("pc.open_url", "downloads", address, f"Brauzerda ochish: {address}")
    folder = _folder(norm)
    file_match = _QUOTED_FILE.search(text) or _FILE.search(
        text.replace(url.group(0), "") if url else text
    )
    if file_match and has_open and (folder or re.search(_PC, norm)):
        name = file_match.group(1).strip()
        root = folder or "downloads"
        if safe_file_name(name):
            return PcCommand(
                "pc.open_file",
                root,
                name,
                f"«{FOLDER_NAMES[root]}» papkasidagi «{name}» faylini ochish",
            )
    if folder and re.search(_LIST, norm) and not has_open:
        return PcCommand(
            "pc.list_folder",
            folder,
            None,
            f"«{FOLDER_NAMES[folder]}» papkasidagi fayllar ro‘yxatini ko‘rish",
        )
    if has_open and (re.search(_PC, norm) or re.search(r"dastur|программ|app\b", norm)):
        for app, words in APP_WORDS:
            if re.search(words, norm):
                return PcCommand(
                    "pc.open_app", "downloads", app, f"«{APP_NAMES[app]}» dasturini ochish"
                )
    if has_open:
        for app, words in APP_WORDS[:4]:  # unambiguous app names need no "kompyuter"
            if re.search(words, norm):
                return PcCommand(
                    "pc.open_app", "downloads", app, f"«{APP_NAMES[app]}» dasturini ochish"
                )
    return None
