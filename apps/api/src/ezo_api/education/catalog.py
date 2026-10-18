"""Education materials EZO prepares, and reading a request.

Kinds: a lesson package (plan with timing, lecture notes, exercises, quiz, homework,
rubric, slides), a quiz / practice questions, a syllabus, an assessment rubric and a
personal study plan. Requests are recognised in Uzbek (Latin and Cyrillic), Russian and
English without a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ezo_api.core.text import normalize
from ezo_api.translation.translit import to_latin


@dataclass(frozen=True, slots=True)
class Kind:
    key: str
    names: dict[str, str]
    pattern: re.Pattern[str]
    outputs: tuple[str, ...]
    """docx, xlsx, pptx — what EZO produces for this kind."""


KINDS: tuple[Kind, ...] = (
    Kind(
        "lesson",
        {"uz": "Dars ishlanmasi", "ru": "План урока", "en": "Lesson package"},
        re.compile(
            r"\b(dars (ishlanma|reja|konspekt|paket)\w*|mashg'ulot (ishlanma|reja)\w*|"
            r"lesson (plan|package)s?|план\w* урок\w*|конспект\w* урок\w*|план занятия|"
            r"технологическ\w* карт\w*)"
        ),
        ("docx", "xlsx", "pptx"),
    ),
    Kind(
        "syllabus",
        {"uz": "Sillabus", "ru": "Силлабус", "en": "Syllabus"},
        re.compile(
            r"\b(sillabus\w*|syllabus\w*|силлабус\w*|o'quv dastur\w*|ishchi o'quv dastur\w*|"
            r"рабоч\w* программ\w*|course outline)"
        ),
        ("docx", "xlsx"),
    ),
    Kind(
        "rubric",
        {"uz": "Baholash mezonlari", "ru": "Критерии оценивания", "en": "Assessment rubric"},
        re.compile(
            r"\b(baholash mezon\w*|baholash rubrika\w*|rubrika\w*|rubric\w*|рубрик\w*|"
            r"критери\w* оценива\w*|grading criteria)"
        ),
        ("docx", "xlsx"),
    ),
    Kind(
        "study_plan",
        {"uz": "O'qish rejasi", "ru": "План подготовки", "en": "Study plan"},
        re.compile(
            r"\b(o'qish reja\w*|o'rganish reja\w*|tayyorgarlik reja\w*|tayyorlanish reja\w*|"
            r"study (plan|schedule)|revision plan|план подготовк\w*|план обучени\w*|"
            r"учебн\w* план\w*|график подготовк\w*)"
        ),
        ("docx", "xlsx"),
    ),
    Kind(
        "quiz",
        {"uz": "Test savollari", "ru": "Тест", "en": "Quiz"},
        re.compile(
            r"\b(test (savol|topshiriq)\w*|testlar\w*|test\b|viktorina\w*|quiz\w*|"
            r"nazorat savol\w*|mashq savol\w*|savollar\w* (tuz|tayyorla|yoz)|"
            r"practice questions|exam questions|тест\w*|контрольн\w* вопрос\w*|"
            r"вопрос\w* для (самопроверки|контроля))"
        ),
        ("docx", "xlsx"),
    ),
)
BY_KEY = {kind.key: kind for kind in KINDS}

_MAKE = re.compile(
    r"\b(tuz|tayyorla|yarat|yoz|ishlab chiq|qilib ber|make|create|prepare|write|draft|"
    r"generate|design|составь|подготов|создай|сделай|напиши|разработай|shablon\w*|template|шаблон\w*)"
)
_NOT_EDUCATION = re.compile(
    r"\b(unit test|pytest|test coverage|testlarni ishga|run (the )?tests|kod\w*|code|"
    r"funksiya\w*|function|python|javascript|typescript|api\b)"
)
_QUESTIONS = re.compile(r"\b(\d{1,3})\s*(ta\s+)?([^\W\d]+\s+)?(savol|test|question|вопрос|задани)")
_MINUTES = re.compile(r"\b(\d{1,3})\s*(daqiqa|minut|min\b|minutes?|мин)")
_HOURS = re.compile(r"\b(\d{1,2})\s*(soat|hours?|час)")
_PAIRS = re.compile(r"\b(\d)\s*(para|juftlik|пар)")
_WEEKS = re.compile(r"\b(\d{1,2})\s*(hafta|weeks?|недел)")
_DAYS = re.compile(r"\b(\d{1,3})\s*(kun|days?|дн|день)")
_GRADE = re.compile(
    r"\b(\d{1,2})\s*-?\s*(sinf|kurs|class|grade|класс|курс)\w*|\b(a1|a2|b1|b2|c1|c2)\b"
)
_SLIDES = re.compile(r"\b(taqdimot|slayd|prezentatsiya|presentation|slides?|презентац|слайд)")


@dataclass(slots=True)
class Options:
    questions: int | None = None
    minutes: int | None = None
    weeks: int | None = None
    days: int | None = None
    level: str | None = None
    slides: bool = False


def detect(text: str) -> Kind | None:
    norm = normalize(to_latin(text)) + " " + normalize(text)
    if _NOT_EDUCATION.search(norm):
        return None
    return next((kind for kind in KINDS if kind.pattern.search(norm)), None)


def wants_education(text: str) -> Kind | None:
    """An education material to make: a kind and a making verb ("test tuz", "dars
    ishlanmasini tayyorla", "составь план урока")."""
    kind = detect(text)
    if kind is None:
        return None
    norm = normalize(text)
    return kind if _MAKE.search(norm) or _MAKE.search(normalize(to_latin(text))) else None


def options_from(text: str) -> Options:
    norm = normalize(text)
    options = Options()
    if match := _QUESTIONS.search(norm):
        options.questions = max(1, min(60, int(match.group(1))))
    if match := _MINUTES.search(norm):
        options.minutes = max(5, min(600, int(match.group(1))))
    elif match := _HOURS.search(norm):
        options.minutes = max(5, min(600, int(match.group(1)) * 60))
    elif match := _PAIRS.search(norm):
        options.minutes = int(match.group(1)) * 80  # one "para" is 80 minutes in Uzbek universities
    if match := _WEEKS.search(norm):
        options.weeks = max(1, min(52, int(match.group(1))))
    if match := _DAYS.search(norm):
        options.days = max(1, min(365, int(match.group(1))))
    if match := _GRADE.search(norm):
        options.level = match.group(0).strip()
    options.slides = bool(_SLIDES.search(norm))
    return options
