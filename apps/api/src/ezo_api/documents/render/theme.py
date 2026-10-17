"""EZO presentation themes (original palettes and type scale).

Design rules: strong hierarchy, large type, generous margins, one accent at a
time, readable contrast. Sizes are in points on a 960×540 pt (16:9) canvas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    background: str
    surface: str
    ink: str
    muted: str
    accent: str
    accent2: str
    highlight: str
    line: str
    dark: bool
    chart: tuple[str, ...]


THEMES: dict[str, Theme] = {
    # Samarkand turquoise and lapis on warm white — EZO's own look.
    "ezo": Theme(
        "ezo",
        "#F7F5F0",
        "#FFFFFF",
        "#16202B",
        "#5A6675",
        "#0F8F86",
        "#2F55C8",
        "#E2A33B",
        "#DCD8CF",
        False,
        ("#0F8F86", "#2F55C8", "#E2A33B", "#C2553D", "#6B5BB5", "#5A6675"),
    ),
    "midnight": Theme(
        "midnight",
        "#0E1520",
        "#172131",
        "#F2F5F8",
        "#9AA6B5",
        "#2EC4B6",
        "#6E8BFF",
        "#F2B544",
        "#2A3647",
        True,
        ("#2EC4B6", "#6E8BFF", "#F2B544", "#F07A5F", "#B49CFF", "#9AA6B5"),
    ),
    # Formal, for government and official audiences: white, deep blue, a little gold.
    "civic": Theme(
        "civic",
        "#FFFFFF",
        "#F3F6FA",
        "#14213D",
        "#556175",
        "#1B4D9C",
        "#2A9D8F",
        "#C9A227",
        "#D5DCE6",
        False,
        ("#1B4D9C", "#2A9D8F", "#C9A227", "#8C5E9C", "#D06A4E", "#556175"),
    ),
    "paper": Theme(
        "paper",
        "#FBF8F2",
        "#FFFFFF",
        "#2A2522",
        "#6E655E",
        "#B5532E",
        "#2E5E4E",
        "#D9A441",
        "#E6DED2",
        False,
        ("#B5532E", "#2E5E4E", "#D9A441", "#4E6E9C", "#8A6E5E", "#6E655E"),
    ),
    # Investor decks: dark, confident, one vivid accent.
    "pitch": Theme(
        "pitch",
        "#101014",
        "#1B1B22",
        "#FFFFFF",
        "#A3A3B2",
        "#7C5CFF",
        "#22D3EE",
        "#F97316",
        "#2C2C36",
        True,
        ("#7C5CFF", "#22D3EE", "#F97316", "#34D399", "#F472B6", "#A3A3B2"),
    ),
}

_HINTS = (
    (
        "civic",
        (
            "hokim",
            "vazir",
            "davlat",
            "rasmiy",
            "government",
            "ministry",
            "official",
            "хоким",
            "министр",
            "государ",
            "официал",
        ),
    ),
    ("pitch", ("investor", "pitch", "startup", "стартап", "инвест", "raund", "funding")),
    (
        "paper",
        ("dars", "talaba", "o'quv", "o‘quv", "lesson", "teacher", "education", "урок", "обучен"),
    ),
    ("midnight", ("dark", "tungi", "qorong", "тёмн", "cinematic")),
)


def choose_theme(*hints: str) -> Theme:
    text = " ".join(hints).lower()
    if text.strip() in THEMES:
        return THEMES[text.strip()]
    for name, words in _HINTS:
        if any(word in text for word in words):
            return THEMES[name]
    return THEMES["ezo"]


@dataclass(frozen=True, slots=True)
class TypeScale:
    title: float = 36
    title_min: float = 24
    subtitle: float = 20
    body: float = 22
    body_min: float = 14
    caption: float = 12
    caption_min: float = 10
    huge: float = 110
    footer: float = 9


TYPE = TypeScale()


def hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def mix(color: str, other: str, amount: float) -> str:
    """Blend `amount` (0..1) of `other` into `color`."""
    a, b = hex_rgb(color), hex_rgb(other)
    return "#" + "".join(f"{round(x + (y - x) * amount):02X}" for x, y in zip(a, b, strict=True))


def luminance(color: str) -> float:
    def channel(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in hex_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(background: str) -> str:
    return (
        "#FFFFFF"
        if contrast("#FFFFFF", background) >= contrast("#16202B", background)
        else "#16202B"
    )
