"""Personality profile loading (config/personality.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ContextMode = Literal["casual", "professional", "technical", "teacher"]
HumorLevel = Literal["off", "light", "normal"]


@dataclass(frozen=True, slots=True)
class ModeStyle:
    label: str
    style: str


@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    name: str
    tagline: str
    identity: str
    traits: tuple[str, ...]
    rules: tuple[str, ...]
    humor: HumorLevel
    humor_levels: dict[str, str]
    modes: dict[str, ModeStyle]
    languages: dict[str, str]

    def mode(self, mode: ContextMode) -> ModeStyle:
        return self.modes.get(mode) or self.modes["casual"]


class PersonalityConfigError(ValueError):
    pass


def load_personality(path: Path) -> PersonalityProfile:
    try:
        raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PersonalityConfigError(f"Personality file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise PersonalityConfigError(f"{path} is not valid TOML: {exc}") from exc

    modes = {
        key: ModeStyle(str(value.get("label", key)), str(value.get("style", "")))
        for key, value in (raw.get("modes") or {}).items()
    }
    if "casual" not in modes:
        raise PersonalityConfigError(f"{path}: a [modes.casual] section is required")
    humor = raw.get("humor", "light")
    if humor not in ("off", "light", "normal"):
        raise PersonalityConfigError(f"{path}: humor must be off, light or normal")
    return PersonalityProfile(
        name=str(raw.get("name", "EZO")),
        tagline=str(raw.get("tagline", "")),
        identity=" ".join(str(raw.get("identity", "")).split()),
        traits=tuple(str(t) for t in raw.get("traits", [])),
        rules=tuple(str(r) for r in raw.get("rules", [])),
        humor=humor,
        humor_levels={str(k): str(v) for k, v in (raw.get("humor_levels") or {}).items()},
        modes=modes,
        languages={str(k): str(v) for k, v in (raw.get("languages") or {}).items()},
    )
