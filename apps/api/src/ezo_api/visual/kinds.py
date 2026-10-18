"""What kind of visual a request asks for (uz / en / ru rules), and its defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ezo_api.core.text import normalize

VisualKind = Literal["image", "hero", "product", "logo", "social", "diagram"]
COMPOSED_KINDS = frozenset({"logo", "social", "diagram"})
"""Kinds EZO lays out itself (text drawn by EZO, picture optional)."""

_KIND_RULES: list[tuple[VisualKind, re.Pattern[str]]] = [
    (
        "diagram",
        re.compile(
            r"\b(diagramm?a|sxema|chizma|flowchart|flow chart|diagram|block scheme|"
            r"arxitektura\s+sxema|architecture diagram|jarayon\s+sxema|схем|диаграмм|блок-схем)"
        ),
    ),
    ("logo", re.compile(r"\b(logo|logotip|логотип|brand mark|emblem|эмблем)")),
    (
        "social",
        re.compile(
            r"\b(instagram|telegram|facebook|linkedin|tiktok|post\w*|story|stories|banner|"
            r"poster|afisha|e'lon uchun|ijtimoiy tarmoq|social media|сторис|пост|баннер|афиш)"
        ),
    ),
    (
        "product",
        re.compile(r"\b(mahsulot|product shot|product photo|product image|товар|продукт\w* фото)"),
    ),
    (
        "hero",
        re.compile(
            r"\b(hero|sayt uchun|website (header|banner|image)|landing|bosh sahifa|обложк\w* сайт)"
        ),
    ),
]

_EDIT = re.compile(
    r"\b(o'zgartir|tahrirla|fon\w*|orqa fon|rangini|rangli|yorqin|qo'sh|olib tashla|almashtir|"
    r"yaxshila|kattalashtir|edit|change|remove|replace|add|make it|background|brighter|"
    r"darker|измени|убери|добавь|замени|фон|сделай)"
)
_DEICTIC = re.compile(
    r"\b(bu|shu|ushbu|oxirgi|this|that|the (image|picture|logo|graphic)|it\b|its\b|"
    r"эт[оуи]|эту|его)"
)
_VISUAL_NOUN = re.compile(
    r"\b(rasm\w*|surat\w*|image|picture|photo|logo\w*|banner|post\w*|diagramm?a|"
    r"картинк\w*|изображени\w*|фото|логотип\w*)"
)
_COUNT = re.compile(r"\b([2-8])\s*(?:ta|x|×|variant|options?|versions?|вариант)")
_ASPECT = re.compile(r"\b(1:1|4:3|3:4|16:9|9:16|4:5|3:2|2:3)\b")
_SQUARE = re.compile(r"\b(kvadrat|square|квадрат)")
_PORTRAIT = re.compile(r"\b(vertikal|portrait|vertical|вертикал)")
_LANDSCAPE = re.compile(r"\b(gorizontal|landscape|horizontal|wide|keng|горизонтал)")
NO_IMAGES = re.compile(r"\b(rasmsiz|rasmlarsiz|without (images|pictures)|no images|без картин)")

_SOCIAL_STORY = re.compile(r"\b(story|stories|reels|tiktok|сторис)")
_SOCIAL_LANDSCAPE = re.compile(r"\b(linkedin|twitter|youtube|banner|баннер|telegram kanal)")
_SOCIAL_PORTRAIT = re.compile(r"\b(poster|afisha|афиш)")

DEFAULT_ASPECT: dict[str, str] = {
    "image": "1:1",
    "hero": "16:9",
    "product": "1:1",
    "logo": "1:1",
    "social": "1:1",
    "diagram": "16:9",
}


@dataclass(frozen=True, slots=True)
class VisualRequest:
    kind: VisualKind
    aspect_ratio: str
    count: int
    social_format: str


def detect_kind(text: str) -> VisualKind:
    norm = normalize(text)
    for kind, pattern in _KIND_RULES:
        if pattern.search(norm):
            return kind
    return "image"


def detect_aspect(text: str, kind: str) -> str:
    norm = normalize(text)
    match = _ASPECT.search(norm)
    if match:
        return match.group(1)
    if _SQUARE.search(norm):
        return "1:1"
    if _PORTRAIT.search(norm):
        return "3:4"
    if _LANDSCAPE.search(norm):
        return "16:9"
    return DEFAULT_ASPECT[kind]


def social_format(text: str) -> str:
    norm = normalize(text)
    if _SOCIAL_STORY.search(norm):
        return "story"
    if _SOCIAL_LANDSCAPE.search(norm):
        return "landscape"
    if _SOCIAL_PORTRAIT.search(norm) or "4:5" in norm:
        return "portrait"
    return "square"


def detect_request(text: str, max_count: int) -> VisualRequest:
    kind = detect_kind(text)
    match = _COUNT.search(normalize(text))
    count = min(int(match.group(1)), max_count) if match else 1
    fmt = social_format(text) if kind == "social" else "square"
    return VisualRequest(kind, detect_aspect(text, kind), max(1, count), fmt)


def wants_edit(text: str) -> bool:
    """An instruction to change an existing visual (needs one to exist)."""
    norm = normalize(text)
    if not _EDIT.search(norm):
        return False
    # "Logo yarat, fonni ko'k qil" creates; "bu rasmni ..." / "fonini ..." edits.
    creating = re.search(r"\b(yarat|chiz|yasa|generate|create|draw|нарисуй|создай|сгенерир)", norm)
    return bool(_DEICTIC.search(norm) or not creating or not _VISUAL_NOUN.search(norm))


def wants_no_images(text: str) -> bool:
    return bool(NO_IMAGES.search(normalize(text)))
