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
    "artifact_not_created": {
        "uz": "⚠️ Fayl yaratilmadi ({error}). Hech narsa saqlanmadi.",
        "en": "⚠️ No file was created ({error}). Nothing was saved.",
        "ru": "⚠️ Файл не создан ({error}). Ничего не сохранено.",
    },
    "all_providers_failed": {
        "uz": "AI provayderlarning hech biri javob bermadi.",
        "en": "None of the AI providers answered.",
        "ru": "Ни один AI-провайдер не ответил.",
    },
    "hint_auth": {
        "uz": "AI kaliti rad etildi. .env faylidagi kalitni tekshiring: Gemini kaliti "
        "aistudio.google.com/apikey dan olinadi va «AIza» bilan boshlanadi; OpenAI kaliti "
        "«sk-» bilan boshlanadi. Keyin: docker compose up -d --force-recreate api",
        "en": "The AI key was rejected. Check the key in .env: a Gemini key comes from "
        "aistudio.google.com/apikey and starts with “AIza”; an OpenAI key starts with “sk-”. "
        "Then run: docker compose up -d --force-recreate api",
        "ru": "Ключ AI отклонён. Проверьте ключ в .env: ключ Gemini берётся на "
        "aistudio.google.com/apikey и начинается с «AIza»; ключ OpenAI начинается с «sk-». "
        "Затем: docker compose up -d --force-recreate api",
    },
    "hint_model": {
        "uz": "Model nomi bu kalit uchun mavjud emas (apps/api/config/models.toml).",
        "en": "A model name is not available. Check apps/api/config/models.toml.",
        "ru": "Модель недоступна для этого ключа (apps/api/config/models.toml).",
    },
    "hint_rate": {
        "uz": "Provayder so‘rovlarni cheklayapti yoki hisobda kredit qolmagan. "
        "Birozdan keyin urinib ko‘ring.",
        "en": "The provider is rate limiting or the account has no credit. Try again later.",
        "ru": "Провайдер ограничивает запросы или на счёте нет кредита. Повторите позже.",
    },
    "hint_network": {
        "uz": "Provayderga ulanib bo‘lmadi. Internet aloqasini tekshiring.",
        "en": "Could not reach the provider. Check your internet connection.",
        "ru": "Не удалось связаться с провайдером. Проверьте интернет.",
    },
    "hint_other": {
        "uz": "Tafsilotlar API loglarida (Sozlamalar → Debug urinishlarni ko‘rsatadi).",
        "en": "See the API logs for details (Settings → Debug shows the attempts).",
        "ru": "Подробности в логах API (Настройки → Debug показывает попытки).",
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
