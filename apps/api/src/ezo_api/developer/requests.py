"""What a request to build software looks like (shared by the intent classifier and the
Developer Agent, so both agree).

Uzbek puts the verb last ("kafe uchun sayt tuzib ber"), English and Russian put it first
("build me a landing page", "сделай сайт"). Words that turn the request into something else
("saytni tarjima qil", "o'quv dasturi tuz") are excluded.
"""

from __future__ import annotations

import re

from ezo_api.core.text import normalize

_NOUN_UZ = (
    r"(veb-?sayt|web-?sayt|website|web-?site|web ?app|web ilova|landing|sayt|portfolio|"
    r"dastur|programma|ilova|app|bot|o'yin|game|skript|script|kalkulyator|to-?do|backend|"
    r"frontend|сайт|программ|приложени|бот|игр|скрипт|лендинг|дастур|илова)"
)
_VERB_UZ = (
    r"(tuz|yarat|yasa|yoz|tayyorla|qur|ishlab chiq|qilib ber|qil\b|qiling|кил|туз|ярат|ёз|"
    r"build|create|make|code)"
)
# Words between the noun and the verb that mean another task on the same thing.
_OTHER_TASK = r"(?!tarjima|tahlil|o'qi|xulosa|tekshir|ko'r|tushuntir|o'rgan|baho|translat|analy)"
_NOUN_FIRST = re.compile(rf"\b{_NOUN_UZ}\w*(?:\s+{_OTHER_TASK}\S+){{0,2}}?\s+{_VERB_UZ}")
_VERB_FIRST = re.compile(
    r"\b(build|create|make|write|code|develop|generate|сделай|создай|напиши|разработай|"
    r"построй)\b(?:\s+\S+){0,4}?\s+"
    r"(website|web ?site|web ?app|landing( page)?|app\b|application|bot\b|game\b|program\b|"
    r"script\b|calculator|to-?do|portfolio|backend|frontend|api\b|сайт|приложени|бот|игр|"
    r"программ|скрипт|калькулятор|лендинг)"
)
_NOT_SOFTWARE = re.compile(
    r"\b(o'quv|ta'lim|ish|dars|tv|teleko'rsatuv|ko'rsatuv|tadbir|konsert|sayohat|"
    r"training|study|tour|учебн|телепрограмм)\w* (dastur|programma|program|программ)"
)


def is_build_request(text: str) -> bool:
    """A request to make a new program, website, bot or app (not a question about code)."""
    norm = normalize(text)
    if _NOT_SOFTWARE.search(norm):
        return False
    return bool(_NOUN_FIRST.search(norm) or _VERB_FIRST.search(norm))
