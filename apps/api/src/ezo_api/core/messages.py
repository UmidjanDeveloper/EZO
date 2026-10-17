"""Fixed user-facing texts produced by EzoCore itself (not by a model)."""

from __future__ import annotations

_TEXTS: dict[str, dict[str, str]] = {
    "refusal": {
        "uz": "Kechirasiz, bu so'rov bo'yicha yordam bera olmayman.",
        "en": "Sorry, I can't help with that request.",
        "ru": "Извините, с этим запросом я помочь не могу.",
    },
    "empty_reply": {
        "uz": "Model bo'sh javob qaytardi. Iltimos, savolni boshqacha yozib ko'ring.",
        "en": "The model returned an empty reply. Please try rephrasing.",
        "ru": "Модель вернула пустой ответ. Попробуйте переформулировать.",
    },
    "truncated": {
        "uz": "_(Javob uzunlik chegarasiga yetib kesildi. “Davom et” deb yozing.)_",
        "en": "_(The reply hit the length limit and was cut off. Say “continue”.)_",
        "ru": "_(Ответ достиг лимита длины и был обрезан. Напишите «продолжай».)_",
    },
    "all_providers_failed": {
        "uz": "AI provayderlarning hech biri javob bermadi.",
        "en": "None of the AI providers answered.",
        "ru": "Ни один AI-провайдер не ответил.",
    },
    "stream_interrupted": {
        "uz": "Javob yozilayotganda provayder bilan aloqa uzildi.",
        "en": "The connection to the provider broke while the reply was being written.",
        "ru": "Связь с провайдером прервалась во время ответа.",
    },
    "config_error": {
        "uz": "Model sozlamalarida xato bor.",
        "en": "There is a problem in the model configuration.",
        "ru": "Ошибка в настройках моделей.",
    },
}


def text(key: str, language: str) -> str:
    variants = _TEXTS[key]
    return variants.get(language) or variants["en"]
