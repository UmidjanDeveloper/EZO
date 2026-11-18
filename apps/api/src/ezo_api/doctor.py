"""`python -m ezo_api.doctor`: the owner's one-command check of a running EZO.

Run inside the API container:

    docker compose exec api python -m ezo_api.doctor

It reports, in Uzbek (or English with --lang en), whether the AI keys reached the API, whether
they look like keys the providers issue, whether each provider accepts its key (one tiny real
request each; skip with --no-probe), and which voice, OCR and Office capabilities are on.
Nothing about a key's value is printed: only its length and whether its prefix matches.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from typing import Any

from ezo_api.providers.registry import KNOWN_PROVIDERS, key_warnings
from ezo_api.settings import Settings

_TEXT: dict[str, dict[str, str]] = {
    "title": {"uz": "EZO tekshiruvi", "en": "EZO check"},
    "keys": {"uz": "AI kalitlari (.env → API)", "en": "AI keys (.env → API)"},
    "missing": {
        "uz": "yo‘q — .env fayli docker-compose.yml yonida bo‘lishi va nomi aynan .env bo‘lishi "
        "kerak (.env.txt yoki .env.example emas)",
        "en": "missing — .env must sit next to docker-compose.yml and be named exactly .env "
        "(not .env.txt or .env.example)",
    },
    "present": {"uz": "bor ({n} belgi)", "en": "present ({n} characters)"},
    "shape_bad": {
        "uz": "ko‘rinishi noto‘g‘ri: {name} kaliti odatda «{prefix}» bilan boshlanadi",
        "en": "does not look right: a {name} key usually starts with “{prefix}”",
    },
    "probe": {
        "uz": "Provayder javobi (kichik haqiqiy so‘rov)",
        "en": "Provider answer (tiny real request)",
    },
    "ok": {"uz": "ishlayapti", "en": "works"},
    "auth": {
        "uz": "KALIT RAD ETILDI — yangi kalit oling va .env ga yozing",
        "en": "KEY REJECTED — get a new key and put it in .env",
    },
    "other": {"uz": "xato: {kind}", "en": "error: {kind}"},
    "none": {
        "uz": "Hech qanday AI kaliti yo‘q: EZO oflayn rejimda "
        "(javoblar, agentlar, tarjima ishlamaydi).",
        "en": "No AI key at all: EZO is offline (no answers, agents or translation).",
    },
    "voice": {"uz": "Ovoz", "en": "Voice"},
    "stt": {"uz": "nutqni tanish", "en": "speech to text"},
    "tts": {"uz": "ovoz chiqarish", "en": "text to speech"},
    "browser": {
        "uz": "yo‘q — brauzer ovozi ishlatiladi",
        "en": "none — the browser's voice is used",
    },
    "uz_voice": {
        "uz": "o‘zbekcha server ovozi: {state}",
        "en": "Uzbek server voice: {state}",
    },
    "uz_on": {"uz": "yoqilgan", "en": "on"},
    "uz_off": {
        "uz": "o‘chiq (yoqish: EZO_ELEVENLABS_TTS_LANGUAGES=uz,en,ru va "
        "EZO_ELEVENLABS_TTS_MODEL_UZ=eleven_v3, yoki OPENAI_API_KEY)",
        "en": "off (turn on: EZO_ELEVENLABS_TTS_LANGUAGES=uz,en,ru and "
        "EZO_ELEVENLABS_TTS_MODEL_UZ=eleven_v3, or OPENAI_API_KEY)",
    },
    "docs": {"uz": "Hujjatlar", "en": "Documents"},
    "ocr": {"uz": "skan/rasm matnini o‘qish (OCR)", "en": "reading scans/images (OCR)"},
    "office": {"uz": "Office → PDF", "en": "Office → PDF"},
    "on": {"uz": "bor", "en": "available"},
    "off": {"uz": "yo‘q", "en": "not available"},
    "restart": {
        "uz": ".env o‘zgarsa: docker compose up -d --force-recreate api",
        "en": "After changing .env: docker compose up -d --force-recreate api",
    },
}

_PREFIX = {"gemini": "AIza", "openai": "sk-", "anthropic": "sk-ant-"}


def _t(lang: str) -> Callable[..., str]:
    def text(key: str, **values: Any) -> str:
        variants = _TEXT[key]
        return (variants.get(lang) or variants["en"]).format(**values)

    return text


async def run(
    settings: Settings,
    lang: str = "uz",
    probe: bool = True,
    providers: dict[str, Any] | None = None,
) -> tuple[list[str], bool]:
    """The report lines, and whether everything needed for answers works."""
    from ezo_api.services import build_services

    t = _t(lang)
    lines = [t("title"), "", t("keys")]
    keys = {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    warnings = key_warnings(settings)
    for name, secret in keys.items():
        value = secret.get_secret_value().strip() if secret else ""
        if not value:
            state = t("missing") if name == "gemini" else "—"
        else:
            state = t("present", n=len(value))
            if name in warnings:
                state += "; " + t("shape_bad", name=KNOWN_PROVIDERS[name], prefix=_PREFIX[name])
        lines.append(f"  {KNOWN_PROVIDERS[name]}: {state}")

    services = build_services(settings, providers)
    router = services.router
    healthy = False
    if router.is_offline:
        lines += ["", t("none")]
    elif probe:
        lines += ["", t("probe")]
        for name in sorted(router.providers):
            result = await router.probe(name)
            healthy = healthy or result == "ok"
            word = (
                t("ok")
                if result == "ok"
                else t("auth")
                if result == "auth"
                else t("other", kind=result)
            )
            lines.append(f"  {KNOWN_PROVIDERS.get(name, name)}: {word}")
    else:
        healthy = True

    voice = services.voice
    lines += ["", t("voice")]
    stt = ", ".join(getattr(p, "name", "?") for p in voice.stt) or t("browser")
    tts = ", ".join(getattr(p, "name", "?") for p in voice.tts) or t("browser")
    lines.append(f"  {t('stt')}: {stt}")
    lines.append(f"  {t('tts')}: {tts}")
    uz = any(
        bool(check("uz")) if callable(check := getattr(p, "supports_language", None)) else True
        for p in voice.tts
    )
    lines.append("  " + t("uz_voice", state=t("uz_on") if uz else t("uz_off")))

    lines += ["", t("docs")]
    ocr = services.ocr.status()
    office = services.office.status() if services.office else {"available": False}
    lines.append(f"  {t('ocr')}: {t('on') if ocr.get('available') else t('off')}")
    lines.append(f"  {t('office')}: {t('on') if office.get('available') else t('off')}")

    lines += ["", t("restart")]
    await services.db.dispose()
    return lines, healthy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ezo_api.doctor", description=__doc__)
    parser.add_argument("--lang", choices=("uz", "en"), default="uz")
    parser.add_argument("--no-probe", action="store_true", help="do not call the providers")
    args = parser.parse_args(argv)
    lines, healthy = asyncio.run(run(Settings(), args.lang, probe=not args.no_probe))
    print("\n".join(lines))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
