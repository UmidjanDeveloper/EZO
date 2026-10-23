"""Lightweight language detection for Uzbek, English and Russian.

Heuristic and dependency-free. Designed to be replaced by a model-based
detector later; callers only depend on `detect_language`.

Voice turns are often only a few words long ("Ha", "Okay", "Спасибо"), so
the detector scores short, common words and script features, and returns the
caller's `fallback` (e.g. the language the speech recogniser reported, or the
conversation's last language) when the text carries no evidence at all.
"""

from __future__ import annotations

from typing import Literal

from ezo_api.core.text import normalize, tokenize

Language = Literal["uz", "en", "ru"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("uz", "en", "ru")
DEFAULT_LANGUAGE: Language = "uz"

# Letters that only appear in Uzbek Cyrillic.
_UZ_CYRILLIC = set("ўқғҳ")
# Letters of Russian that the Uzbek Cyrillic alphabet does not use.
_RU_ONLY = set("ыщь")

_UZ_WORDS = set(
    """
    men sen siz biz u bu va uchun bilan emas yo'q ha qanday nima nega qachon qayerda kerak
    mumkin bor edi qilamiz qil qiling ber bering tayyorla yordam salom rahmat yaxshi juda
    menga sizga mening sening bizning ham lekin agar endi bugun ertaga kecha qilib haqida
    tushuntir top oxirgi qaror qarorini nechta qaysi kim boshla davom qani yoz yasab o'zbek
    tilida qanaqa qalaysan qalesan assalomu alaykum xayr iltimos ko'p kam bo'ladi bo'lsa
    qiladi nimaga shu o'sha yana faqat hammasi loyiha loyiham eslab qol
    xo'p mayli albatta uzr gap och yop qo'y ayt aytib keyingi oldingi ovoz baland past
    havo ob qancha qayer kimsan kimsiz yaxshimisiz qalaysiz zo'r rahmat raxmat sekin tez
    hozir keyin oldin kun hafta oy yil vaqt soat bo'ldi kel ket bilasanmi bilasizmi
    """.split()
)
_UZ_SUFFIXES = tuple(
    "lar larni ning dagi ni ga da dan imiz ingiz yapman yapti moqda sizmi mi chi man san "
    "miz misiz mising yapsiz dingiz dim sizlar".split()
)
_EN_WORDS = set(
    """
    the a an is are was were i you we they it and or but to of in on for with what how why
    when where please can could would should do does my your this that hello hi thanks
    let's let me help about make write explain find speaking practice want need have be
    yes no okay ok sure go ahead good morning evening night bye goodbye great job nice meet
    thank sorry who which there here now today tomorrow tell show open close play stop start
    turn up down weather time news joke story music song read just really very much well
    right hey also not all some any more again fine cool awesome perfect
    """.split()
)
_EN_CONTRACTIONS = ("'s", "n't", "'re", "'m", "'ll", "'ve", "'d")

_RU_WORDS = set(
    """
    я ты вы он она оно мы они что как где когда почему зачем это не да нет привет спасибо
    хорошо пожалуйста кто такой такая мне меня тебя тебе нам вам мой твой свой и в на с по
    из за для о об от до но или если уже ещё еще очень можно нужно надо сейчас сегодня
    завтра вчера здравствуй здравствуйте пока ладно давай скажи расскажи открой закрой
    включи выключи сделай помоги покажи найди погода время дела
    """.split()
)
_UZ_CYR_WORDS = set(
    """
    мен сен сиз биз у бу ва учун билан эмас йўқ ҳа қандай нима нега қачон қаерда керак
    мумкин бор эди қил қилинг бер беринг ёрдам салом раҳмат рахмат яхши жуда менга сизга
    менинг сенинг ҳам лекин агар энди бугун эртага кеча ҳақида топ қайси ким бошла давом
    қани ёз ўзбек тилида қанақа қалайсан қалайсиз ассалому алайкум хайр илтимос кўп кам
    бўлади нимага шу ўша яна фақат ҳаммаси хўп майли албатта узр гап оч ёп айт кимсан
    яхшимисиз ҳозир кейин уйдаман
    """.split()
)
_UZ_CYR_SUFFIXES = tuple(
    "лар ларни нинг даги ман сан миз сиз мисиз япман япти моқда дим дингиз ганман".split()
)


def _pick(uz: float, other: float, other_language: Language, fallback: Language) -> Language:
    if uz == 0 and other == 0:
        return fallback
    if uz == other:
        return fallback if fallback in ("uz", other_language) else "uz"
    return "uz" if uz > other else other_language


def _cyrillic(lowered: str, tokens: list[str], fallback: Language) -> Language:
    if any(ch in _UZ_CYRILLIC for ch in lowered):
        return "uz"
    ru = 2.0 * sum(1 for ch in _RU_ONLY if ch in lowered)
    uz = 0.0
    for token in tokens:
        if token in _RU_WORDS:
            ru += 1.0
        if token in _UZ_CYR_WORDS:
            uz += 1.0
        elif len(token) > 4 and token.endswith(_UZ_CYR_SUFFIXES):
            uz += 0.5
    # Cyrillic text with no evidence either way is far more often Russian.
    return _pick(uz, ru, "ru", fallback if fallback in ("uz", "ru") else "ru")


def _latin(tokens: list[str], fallback: Language) -> Language:
    uz = 0.0
    en = 0.0
    for token in tokens:
        if token in _UZ_WORDS or "o'" in token or "g'" in token:
            uz += 1.0
        elif len(token) > 4 and token.endswith(_UZ_SUFFIXES):
            uz += 0.5
        elif "q" in token or ("x" in token and not token.startswith("ex")):
            uz += 0.5  # q and x are everyday Uzbek letters, rare in English
        if token in _EN_WORDS or token.endswith(_EN_CONTRACTIONS):
            en += 1.0
        elif "w" in token or "th" in token or ("c" in token.replace("ch", "")):
            en += 0.5  # Uzbek Latin has no w, no th and no c outside "ch"
    return _pick(uz, en, "en", fallback)


def detect_language(text: str, fallback: Language = DEFAULT_LANGUAGE) -> Language:
    """Return the most likely language of `text` (uz, en or ru).

    `fallback` is returned when the text gives no evidence (and breaks ties).
    """
    lowered = normalize(text)
    letters = [ch for ch in lowered if ch.isalpha()]
    if not letters:
        return fallback
    tokens = tokenize(text)
    cyrillic = sum(1 for ch in letters if "а" <= ch <= "я" or ch in "ёўқғҳ")
    if cyrillic / len(letters) > 0.5:
        return _cyrillic(lowered, tokens, fallback)
    return _latin(tokens, fallback)


def as_language(code: str | None) -> Language | None:
    """Map a provider's language code or name ("uzb", "russian", "en-US") to uz/en/ru."""
    if not code:
        return None
    key = code.strip().lower().replace("_", "-").split("-")[0]
    return _CODES.get(key)


_CODES: dict[str, Language] = {
    "uz": "uz",
    "uzb": "uz",
    "uzbek": "uz",
    "en": "en",
    "eng": "en",
    "english": "en",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
}
