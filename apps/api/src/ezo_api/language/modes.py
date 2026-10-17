# ruff: noqa: E501  (regex and guide text are kept on one line each)
"""Practice modes, CEFR levels and learner commands — decided from the text, no model call."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ezo_api.core.text import normalize

Mode = Literal[
    "free_conversation",
    "ielts",
    "teacher",
    "grammar",
    "vocabulary",
    "debate",
    "job_interview",
    "travel",
    "business",
]
Command = Literal["practice", "finish", "progress"]

_MODES: tuple[tuple[Mode, re.Pattern[str]], ...] = (
    ("ielts", re.compile(r"\b(ielts|mock (speaking )?test|speaking test|speaking exam)")),
    (
        "job_interview",
        re.compile(r"\b(job interview|interview practice|ish (uchun )?suhbat|собеседован)"),
    ),
    ("business", re.compile(r"\b(business english|biznes ingliz|деловой англ|business meeting)")),
    ("debate", re.compile(r"\b(debate|munozara|bahslash|дебат|спорим)")),
    (
        "travel",
        re.compile(r"\b(travel|sayohat|airport|aeroport|hotel|mehmonxona|путешеств|аэропорт)"),
    ),
    ("grammar", re.compile(r"\b(grammar|grammatika|грамматик)")),
    ("vocabulary", re.compile(r"\b(vocabulary|so'z boyligi|lug'at|yangi so'zlar|словар|лексик)")),
    ("teacher", re.compile(r"\b(teach me|o'rgat|dars (o'?t|ber)|lesson|урок|научи)")),
)
_CEFR = re.compile(r"\b([abc][12])\b")
_CEFR_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Most specific first: "upper-intermediate" must not match "intermediate".
    ("A1", re.compile(r"\b(complete beginner|noldan|с нуля)")),
    ("B2", re.compile(r"\b(upper[- ]intermediate)")),
    ("A2", re.compile(r"\b(beginner|boshlang'ich|начинающ)")),
    ("B1", re.compile(r"\b(intermediate|o'rta daraja|средн)")),
    ("C1", re.compile(r"\b(advanced|yuqori daraja|продвинут)")),
)
_FINISH = re.compile(
    r"\b(tugat|yakunla|to'xtat|bas qil|baho(la|ying)?|natijam|feedback|finish|end (the )?"
    r"(session|test|practice)|stop the (test|session)|that's all|i'm done|закончим|заканчива|"
    r"оцени|результат)"
)
_PROGRESS = re.compile(
    r"\b(progress\w*|rivojlan\w*|yaxshilandimi|o'sdimi|natijalarim|statistik\w*|oxirgi \d+ ta|"
    r"eng ko'p (?:\w+\s+){0,4}xato|xatolarim|my (mistakes|progress|results)|have i improved|"
    r"did my \w+ improve|прогресс|мои ошибки|улучшил)"
)
_GOAL = re.compile(
    r"\b(maqsad\w*|goal|target|цель)\b.{0,40}?(ielts\s*(\d(?:[.,]5)?)|band\s*(\d(?:[.,]5)?)|\b([abc][12])\b)"
)


@dataclass(frozen=True, slots=True)
class GoalRequest:
    description: str
    target_band: float | None
    cefr: str | None


def detect_mode(text: str) -> Mode | None:
    """The mode the user asked for, or None when the message does not name one."""
    norm = normalize(text)
    for mode, pattern in _MODES:
        if pattern.search(norm):
            return mode
    return None


def detect_cefr(text: str) -> str | None:
    norm = normalize(text)
    match = _CEFR.search(norm)
    if match:
        return match.group(1).upper()
    for level, pattern in _CEFR_WORDS:
        if pattern.search(norm):
            return level
    return None


def detect_command(text: str, *, has_active_session: bool) -> Command:
    norm = normalize(text)
    if _PROGRESS.search(norm):
        return "progress"
    if has_active_session and _FINISH.search(norm):
        return "finish"
    return "practice"


def detect_goal(text: str) -> GoalRequest | None:
    match = _GOAL.search(normalize(text))
    if not match:
        return None
    band_text = match.group(3) or match.group(4)
    band = float(band_text.replace(",", ".")) if band_text else None
    if band is not None and not 0 < band <= 9:
        band = None
    cefr = match.group(5).upper() if match.group(5) else None
    return GoalRequest(" ".join(text.split())[:300], band, cefr)


MODE_GUIDE: dict[str, str] = {
    "free_conversation": "Have a natural, friendly conversation. Ask one open question at a time and show genuine interest.",
    "ielts": "You are an IELTS-style speaking examiner SIMULATOR (not an official examiner). Be polite, neutral and concise like a real examiner: do not teach, praise or correct during the test.",
    "teacher": "Act as a patient teacher: explain one point at a time with short examples, then check understanding with a quick question.",
    "grammar": "Coach grammar: build the conversation around the learner's weak structures; after the learner answers, you may give ONE short correction if it blocks meaning.",
    "vocabulary": "Coach vocabulary: introduce at most 3 useful words or collocations per turn, use them in context and invite the learner to use them.",
    "debate": "Run a friendly debate: take the opposite position, give one argument at a time and ask the learner to respond.",
    "job_interview": "Act as a professional job interviewer. Ask one realistic interview question at a time and follow up on the answers.",
    "travel": "Role-play travel situations (airport, hotel, restaurant, directions). Play the other person in the scene.",
    "business": "Practise business English: meetings, emails, negotiations and small talk with colleagues. Play the other person.",
}

CEFR_GUIDE: dict[str, str] = {
    "A1": "Learner level A1: very short sentences, the most common words, speak slowly, one simple question at a time; explanations may use the learner's language.",
    "A2": "Learner level A2: short simple sentences, everyday vocabulary, no idioms; rephrase if the learner seems lost.",
    "B1": "Learner level B1: clear everyday English, a few new words per turn, avoid rare idioms.",
    "B2": "Learner level B2: natural English with some idioms and more abstract questions.",
    "C1": "Learner level C1: natural, nuanced English; challenge with abstract and argumentative questions.",
    "C2": "Learner level C2: native-like discussion; precise vocabulary and complex ideas.",
}
