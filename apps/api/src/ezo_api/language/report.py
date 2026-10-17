"""The session report saved as an artifact (Markdown → DOCX + PDF), in the learner's language."""

from __future__ import annotations

from ezo_api.db.models import LanguageSession
from ezo_api.language.analysis import TextMetrics, describe
from ezo_api.language.assessment import Assessment

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "ielts_title": "IELTS-style Speaking Practice",
        "title": "English Practice Session",
        "disclaimer": "Simulator result: all bands are estimates, not an official IELTS score.",
        "range": "Estimated band range",
        "no_band": "No band estimate",
        "criteria": "Criteria (estimates)",
        "fc": "Fluency and Coherence",
        "lr": "Lexical Resource",
        "gra": "Grammatical Range and Accuracy",
        "pr": "Pronunciation",
        "not_assessed": "not assessed",
        "transcript_assisted": "transcript-assisted estimate",
        "level": "Estimated CEFR level",
        "measured": "Measured",
        "strengths": "Strengths",
        "weaknesses": "Weaknesses",
        "mistakes": "Mistakes to work on",
        "better": "Better sentences",
        "vocabulary": "Vocabulary to learn",
        "target": "Practice target",
        "notes": "Notes",
        "mode": "Mode",
    },
    "uz": {
        "ielts_title": "IELTS uslubidagi speaking mashg'uloti",
        "title": "Ingliz tili mashg'uloti",
        "disclaimer": "Simulyator natijasi: barcha ballar taxminiy, rasmiy IELTS balli emas.",
        "range": "Taxminiy band oralig'i",
        "no_band": "Band baholanmadi",
        "criteria": "Mezonlar (taxminiy)",
        "fc": "Fluency and Coherence (ravonlik va izchillik)",
        "lr": "Lexical Resource (so'z boyligi)",
        "gra": "Grammatical Range and Accuracy (grammatika)",
        "pr": "Pronunciation (talaffuz)",
        "not_assessed": "baholanmadi",
        "transcript_assisted": "matn asosidagi taxmin",
        "level": "Taxminiy CEFR darajasi",
        "measured": "O'lchangan ko'rsatkichlar",
        "strengths": "Kuchli tomonlar",
        "weaknesses": "Zaif tomonlar",
        "mistakes": "Ustida ishlash kerak bo'lgan xatolar",
        "better": "Yaxshiroq jumlalar",
        "vocabulary": "O'rganish uchun so'zlar",
        "target": "Keyingi mashq maqsadi",
        "notes": "Izohlar",
        "mode": "Rejim",
    },
    "ru": {
        "ielts_title": "Практика IELTS Speaking (симулятор)",
        "title": "Занятие по английскому языку",
        "disclaimer": "Результат симулятора: все баллы ориентировочные, не официальный балл IELTS.",
        "range": "Ориентировочный диапазон",
        "no_band": "Балл не оценивался",
        "criteria": "Критерии (оценка)",
        "fc": "Fluency and Coherence (беглость и связность)",
        "lr": "Lexical Resource (словарный запас)",
        "gra": "Grammatical Range and Accuracy (грамматика)",
        "pr": "Pronunciation (произношение)",
        "not_assessed": "не оценивалось",
        "transcript_assisted": "оценка по расшифровке",
        "level": "Ориентировочный уровень CEFR",
        "measured": "Измерено",
        "strengths": "Сильные стороны",
        "weaknesses": "Слабые стороны",
        "mistakes": "Ошибки для работы",
        "better": "Как сказать лучше",
        "vocabulary": "Слова для изучения",
        "target": "Цель следующей практики",
        "notes": "Примечания",
        "mode": "Режим",
    },
}


def _band(value: float | None) -> str:
    return f"{value:g}" if value is not None else "—"


def report_title(language_session: LanguageSession, ui_language: str) -> str:
    labels = LABELS.get(ui_language, LABELS["en"])
    title = labels["ielts_title"] if language_session.mode == "ielts" else labels["title"]
    date = language_session.started_at.strftime("%Y-%m-%d")
    return f"{title} — {date}"


def build_report(
    language_session: LanguageSession,
    assessment: Assessment,
    metrics: TextMetrics,
    ui_language: str,
) -> str:
    t = LABELS.get(ui_language, LABELS["en"])
    s = assessment.scores
    lines = [f"# {report_title(language_session, ui_language)}", "", f"*{t['disclaimer']}*", ""]
    if assessment.band_low is not None and assessment.band_high is not None:
        band = (
            f"{assessment.band_low:g}"
            if assessment.band_low == assessment.band_high
            else f"{assessment.band_low:g}–{assessment.band_high:g}"
        )
        lines.append(f"**{t['range']}: {band}**")
    else:
        lines.append(f"**{t['no_band']}**")
    if assessment.cefr_estimate:
        lines.append(f"{t['level']}: {assessment.cefr_estimate}")
    lines += ["", f"{t['mode']}: {language_session.mode}", ""]
    if assessment.summary:
        lines += [assessment.summary, ""]

    pron = (
        t["not_assessed"]
        if s.get("pronunciation") is None
        else f"{_band(s['pronunciation'])} ({t['transcript_assisted']})"
    )
    lines += [
        f"## {t['criteria']}",
        "",
        "| | Band |",
        "|---|---|",
        f"| {t['fc']} | {_band(s.get('fluency_coherence'))} |",
        f"| {t['lr']} | {_band(s.get('lexical_resource'))} |",
        f"| {t['gra']} | {_band(s.get('grammatical_range_accuracy'))} |",
        f"| {t['pr']} | {pron} |",
        "",
        f"## {t['measured']}",
        "",
        describe(metrics),
        "",
    ]

    def bullets(title: str, items: list[str]) -> None:
        if items:
            lines.extend([f"## {title}", "", *[f"- {item}" for item in items], ""])

    bullets(t["strengths"], assessment.strengths)
    bullets(t["weaknesses"], assessment.weaknesses)
    bullets(
        t["mistakes"],
        [
            f"“{m.original}” → “{m.correction}” ({m.category.replace('_', ' ')})"
            + (f" — {m.explanation}" if m.explanation else "")
            for m in assessment.mistakes[:12]
        ],
    )
    bullets(
        t["better"], [f"“{b['original']}” → “{b['improved']}”" for b in assessment.better_sentences]
    )
    bullets(
        t["vocabulary"],
        [
            f"**{v['term']}** — {v['meaning']}" + (f" (*{v['example']}*)" if v["example"] else "")
            for v in assessment.vocabulary
        ],
    )
    if assessment.practice_target:
        lines += [f"## {t['target']}", "", assessment.practice_target, ""]
    bullets(t["notes"], assessment.notes)
    return "\n".join(lines).strip() + "\n"
