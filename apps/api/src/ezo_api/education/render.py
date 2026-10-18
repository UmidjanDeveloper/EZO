"""Education material → Word (Markdown for the document pipeline), Excel sheets and a
slide deck spec. Labels follow the output language; Uzbek Cyrillic is produced by
converting the Uzbek output (`translation.translit`)."""

from __future__ import annotations

from typing import Any

from ezo_api.education.catalog import Kind, Options
from ezo_api.education.models import Check, Material, letter

LABELS: dict[str, dict[str, str]] = {
    "uz": {
        "subject": "Fan", "level": "Daraja", "duration": "Davomiyligi", "minutes": "daqiqa",
        "objectives": "Maqsadlar", "materials": "Kerakli materiallar", "stages": "Dars bosqichlari",
        "stage": "Bosqich", "teacher": "O'qituvchi", "students": "O'quvchilar",
        "notes": "Ma'ruza matni", "exercises": "Mashqlar", "answer": "Javob",
        "quiz": "Test savollari", "homework": "Uyga vazifa", "rubric": "Baholash mezonlari",
        "criterion": "Mezon", "points": "Ball", "max_points": "Maksimal ball",
        "key": "Javoblar kaliti (o'qituvchi uchun)", "question": "Savol",
        "explanation": "Izoh", "weeks": "Haftalik reja", "week": "Hafta", "topic": "Mavzu",
        "activities": "Mashg'ulotlar", "reading": "O'qish uchun", "assessment": "Baholash",
        "component": "Tarkibiy qism", "weight": "Ulushi, %", "policies": "Qoidalar",
        "goal": "Maqsad", "plan": "Reja", "day": "Kun", "task": "Vazifa",
        "total": "Jami", "checkpoints": "Nazorat nuqtalari", "resources": "Manbalar",
        "sources_needed": "Kerakli manbalar (EZO o'ylab topmaydi — o'zingiz qo'shing)",
        "open": "Ochiq savol", "issues": "EZO tekshiruvi", "slides": "Slaydlar",
        "outline": "Javob rejasi", "why": "Nega so'raladi", "defense": "Ehtimoliy savollar",
    },
    "ru": {
        "subject": "Предмет", "level": "Уровень", "duration": "Продолжительность", "minutes": "мин",
        "objectives": "Цели", "materials": "Материалы", "stages": "Этапы урока",
        "stage": "Этап", "teacher": "Учитель", "students": "Ученики",
        "notes": "Конспект", "exercises": "Упражнения", "answer": "Ответ",
        "quiz": "Тест", "homework": "Домашнее задание", "rubric": "Критерии оценивания",
        "criterion": "Критерий", "points": "Баллы", "max_points": "Максимум баллов",
        "key": "Ключ ответов (для учителя)", "question": "Вопрос",
        "explanation": "Пояснение", "weeks": "План по неделям", "week": "Неделя", "topic": "Тема",
        "activities": "Занятия", "reading": "Чтение", "assessment": "Оценивание",
        "component": "Компонент", "weight": "Вес, %", "policies": "Правила",
        "goal": "Цель", "plan": "План", "day": "День", "task": "Задание",
        "total": "Итого", "checkpoints": "Контрольные точки", "resources": "Ресурсы",
        "sources_needed": "Нужные источники (EZO их не придумывает — добавьте сами)",
        "open": "Открытый вопрос", "issues": "Проверка EZO", "slides": "Слайды",
        "outline": "План ответа", "why": "Почему спрашивают", "defense": "Вероятные вопросы",
    },
    "en": {
        "subject": "Subject", "level": "Level", "duration": "Length", "minutes": "min",
        "objectives": "Objectives", "materials": "Materials", "stages": "Lesson stages",
        "stage": "Stage", "teacher": "Teacher", "students": "Students",
        "notes": "Lecture notes", "exercises": "Exercises", "answer": "Answer",
        "quiz": "Quiz", "homework": "Homework", "rubric": "Assessment rubric",
        "criterion": "Criterion", "points": "Points", "max_points": "Maximum points",
        "key": "Answer key (for the teacher)", "question": "Question",
        "explanation": "Explanation", "weeks": "Weekly schedule", "week": "Week", "topic": "Topic",
        "activities": "Activities", "reading": "Reading", "assessment": "Assessment",
        "component": "Component", "weight": "Weight, %", "policies": "Policies",
        "goal": "Goal", "plan": "Plan", "day": "Day", "task": "Task",
        "total": "Total", "checkpoints": "Checkpoints", "resources": "Resources",
        "sources_needed": "Sources needed (EZO does not invent them — add your own)",
        "open": "Open question", "issues": "EZO checks", "slides": "Slides",
        "outline": "Answer outline", "why": "Why it is asked", "defense": "Likely questions",
    },
}  # fmt: skip


def labels(language: str) -> dict[str, str]:
    return LABELS.get("uz" if language.startswith("uz") else language, LABELS["en"])


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip() or " "


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return [*lines, ""]


def _questions(material: Material, t: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for number, question in enumerate(material.questions, start=1):
        lines.append(f"**{number}. {question.question}**")
        lines.append("")
        if question.type == "open":
            lines += [f"*{t['open']}*", ""]
            continue
        lines += [f"- {letter(i)}) {option}" for i, option in enumerate(question.options)]
        lines.append("")
    return lines


def _key(material: Material, check: Check, t: dict[str, str]) -> list[str]:
    rows = []
    for (number, answer), question in zip(check.answer_key, material.questions, strict=False):
        rows.append([str(number), answer, question.explanation])
    return [f"## {t['key']}", "", *_table(["№", t["answer"], t["explanation"]], rows)]


def _criteria(material: Material, check: Check, t: dict[str, str]) -> list[str]:
    rows = [
        [c.criterion, "; ".join(f"{lv.label} ({lv.points}): {lv.description}" for lv in c.levels)]
        for c in material.criteria
    ]
    return [
        *_table([t["criterion"], t["points"]], rows),
        f"**{t['max_points']}: {check.max_points}**",
        "",
    ]


def to_markdown(kind: Kind, material: Material, check: Check, language: str) -> str:
    t = labels(language)
    title = material.title or kind.names.get(language[:2], kind.names["en"])
    lines = [f"# {title}", ""]
    facts = [
        (t["subject"], material.subject),
        (t["level"], material.level),
        (
            t["duration"],
            f"{material.duration_minutes} {t['minutes']}" if material.duration_minutes else "",
        ),
        (t["goal"], material.goal),
    ]
    lines += [f"**{label}:** {value}  " for label, value in facts if value] + [""]
    if material.objectives:
        lines += [f"## {t['objectives']}", "", *[f"- {o}" for o in material.objectives], ""]
    if material.materials:
        lines += [f"## {t['materials']}", "", *[f"- {m}" for m in material.materials], ""]
    if material.stages:
        rows = [[s.name, str(s.minutes), s.teacher, s.students] for s in material.stages]
        rows.append([f"**{t['total']}**", str(check.total_minutes), "", ""])
        lines += [
            f"## {t['stages']}",
            "",
            *_table([t["stage"], t["minutes"], t["teacher"], t["students"]], rows),
        ]
    if material.lecture_notes:
        lines += [f"## {t['notes']}", ""]
        for section in material.lecture_notes:
            if section.heading:
                lines += [f"### {section.heading}", ""]
            lines += [section.text, ""]
    if material.exercises:
        lines += [f"## {t['exercises']}", ""]
        lines += [f"{i}. {e.task}" for i, e in enumerate(material.exercises, start=1)] + [""]
    if material.weeks:
        rows = [
            [str(w.week), w.topic, "; ".join(w.activities), "; ".join(w.reading), w.assessment]
            for w in material.weeks
        ]
        lines += [
            f"## {t['weeks']}",
            "",
            *_table([t["week"], t["topic"], t["activities"], t["reading"], t["assessment"]], rows),
        ]
    if material.assessment:
        rows = [[c.component, str(c.weight)] for c in material.assessment]
        rows.append([f"**{t['total']}**", str(sum(c.weight for c in material.assessment))])
        lines += [f"## {t['assessment']}", "", *_table([t["component"], t["weight"]], rows)]
    if material.policies:
        lines += [f"## {t['policies']}", "", *[f"- {p}" for p in material.policies], ""]
    if material.plan:
        lines += [f"## {t['plan']}", ""]
        for week in material.plan:
            minutes = check.weekly_minutes.get(week.week, 0)
            lines += [f"### {t['week']} {week.week}: {week.focus} ({minutes} {t['minutes']})", ""]
            lines += _table(
                [t["day"], t["task"], t["minutes"]],
                [[s.day, s.task, str(s.minutes)] for s in week.sessions],
            )
    if material.checkpoints:
        lines += [f"## {t['checkpoints']}", "", *[f"- {c}" for c in material.checkpoints], ""]
    if material.homework:
        lines += [f"## {t['homework']}", "", *[f"- {h}" for h in material.homework], ""]
    if material.criteria:
        lines += [f"## {t['rubric']}", "", *_criteria(material, check, t)]
    if material.questions and kind.key == "defense":
        lines += [f"## {t['defense']}", ""]
        for number, question in enumerate(material.questions, start=1):
            lines += [f"**{number}. {question.question}**", ""]
            if question.answer:
                lines += [f"*{t['outline']}:* {question.answer}", ""]
            if question.explanation:
                lines += [f"*{t['why']}:* {question.explanation}", ""]
    elif material.questions:
        lines += [f"## {t['quiz']}", "", *_questions(material, t)]
    if material.exercises and any(e.answer for e in material.exercises):
        rows = [[str(i), e.answer] for i, e in enumerate(material.exercises, start=1)]
        lines += [f"## {t['exercises']} — {t['answer']}", "", *_table(["№", t["answer"]], rows)]
    if material.questions and kind.key != "defense":
        lines += _key(material, check, t)
    resources = material.resources + material.sources_needed
    if resources:
        lines += [f"## {t['sources_needed']}", "", *[f"- {r}" for r in resources], ""]
    return "\n".join(lines).strip() + "\n"


def to_sheets(kind: Kind, material: Material, check: Check, language: str) -> list[dict[str, Any]]:
    """Sheets for the create_spreadsheet tool."""
    t = labels(language)
    sheets: list[dict[str, Any]] = []
    if material.questions:
        rows: list[list[Any]] = []
        for (number, answer), question in zip(check.answer_key, material.questions, strict=False):
            options = [*question.options, "", "", "", ""][:4]
            rows.append([number, question.question, *options, answer, question.explanation])
        sheets.append(
            {
                "name": t["quiz"][:30],
                "columns": ["№", t["question"], "A", "B", "C", "D", t["answer"], t["explanation"]],
                "rows": rows,
            }
        )
    if material.stages:
        sheets.append(
            {
                "name": t["stages"][:30],
                "columns": [t["stage"], t["minutes"], t["teacher"], t["students"]],
                "rows": [[s.name, s.minutes, s.teacher, s.students] for s in material.stages]
                + [[t["total"], check.total_minutes, "", ""]],
            }
        )
    if material.criteria:
        rows = []
        for criterion in material.criteria:
            for level in criterion.levels:
                rows.append([criterion.criterion, level.label, level.points, level.description])
        rows.append([t["max_points"], "", check.max_points, ""])
        sheets.append(
            {
                "name": t["rubric"][:30],
                "columns": [t["criterion"], t["level"], t["points"], t["explanation"]],
                "rows": rows,
            }
        )
    if material.weeks:
        sheets.append(
            {
                "name": t["weeks"][:30],
                "columns": [t["week"], t["topic"], t["activities"], t["reading"], t["assessment"]],
                "rows": [
                    [w.week, w.topic, "; ".join(w.activities), "; ".join(w.reading), w.assessment]
                    for w in material.weeks
                ],
            }
        )
    if material.assessment:
        sheets.append(
            {
                "name": t["assessment"][:30],
                "columns": [t["component"], t["weight"]],
                "rows": [[c.component, c.weight] for c in material.assessment]
                + [[t["total"], sum(c.weight for c in material.assessment)]],
            }
        )
    if material.plan:
        rows = [
            [week.week, week.focus, s.day, s.task, s.minutes]
            for week in material.plan
            for s in week.sessions
        ]
        sheets.append(
            {
                "name": t["plan"][:30],
                "columns": [t["week"], t["topic"], t["day"], t["task"], t["minutes"]],
                "rows": rows,
            }
        )
    return sheets


def to_deck(material: Material, language: str) -> dict[str, Any] | None:
    """A DeckSpec dict for the create_presentation tool (title slide + the model's slides)."""
    if not material.slides:
        return None
    deck_language = language if language in ("uz", "ru", "en") else "uz"
    slides: list[dict[str, Any]] = [
        {
            "layout": "title",
            "title": material.title or "Dars",
            "subtitle": " · ".join(v for v in (material.subject, material.level) if v),
        }
    ]
    for slide in material.slides:
        slides.append(
            {
                "layout": "bullets",
                "title": slide.title,
                "bullets": slide.bullets,
                "speaker_notes": slide.notes,
            }
        )
    return {
        "title": material.title or "Dars",
        "subtitle": material.subject,
        "language": deck_language,
        "audience": material.level or "learners",
        "goal": "teaching",
        "slides": slides,
    }


def blank(kind: Kind, options: Options, language: str) -> Material:
    """A template with the kind's structure and placeholders (no model)."""
    t = labels(language)
    data: dict[str, Any] = {"title": kind.names.get(language[:2], kind.names["en"])}
    if kind.key == "lesson":
        minutes = options.minutes or 45
        parts = [
            ("[Kirish / motivatsiya]", 5),
            ("[Yangi mavzu]", max(5, minutes - 25)),
            ("[Mashq]", 10),
            ("[Mustahkamlash]", 5),
            ("[Xulosa va uyga vazifa]", 5),
        ]
        data |= {
            "subject": "[Fan]",
            "level": options.level or "[Sinf / kurs]",
            "duration_minutes": sum(m for _, m in parts),
            "objectives": ["[Maqsad 1]", "[Maqsad 2]"],
            "materials": ["[Material]"],
            "stages": [
                {
                    "name": n,
                    "minutes": m,
                    "teacher": f"[{t['teacher']}]",
                    "students": f"[{t['students']}]",
                }
                for n, m in parts
            ],
            "homework": ["[Uyga vazifa]"],
        }
    elif kind.key == "quiz":
        data |= {
            "subject": "[Fan]",
            "questions": [
                {"question": f"[{t['question']} {i}]", "options": ["[A]", "[B]", "[C]", "[D]"]}
                for i in range(1, (options.questions or 10) + 1)
            ],
        }
    elif kind.key == "syllabus":
        data |= {
            "subject": "[Fan]",
            "weeks": [
                {"week": i, "topic": f"[{t['topic']}]"} for i in range(1, (options.weeks or 15) + 1)
            ],
            "assessment": [
                {"component": "[Joriy nazorat]", "weight": 30},
                {"component": "[Oraliq nazorat]", "weight": 20},
                {"component": "[Yakuniy nazorat]", "weight": 50},
            ],
        }
    elif kind.key == "rubric":
        levels = [
            {"label": "[A'lo]", "points": 5},
            {"label": "[Yaxshi]", "points": 4},
            {"label": "[Qoniqarli]", "points": 3},
        ]
        data |= {
            "criteria": [
                {"criterion": f"[{t['criterion']} {i}]", "levels": levels} for i in range(1, 5)
            ]
        }
    else:
        data |= {
            "goal": "[Maqsad]",
            "plan": [
                {
                    "week": i,
                    "focus": f"[{t['topic']}]",
                    "sessions": [{"day": f"[{t['day']}]", "task": f"[{t['task']}]", "minutes": 0}],
                }
                for i in range(1, (options.weeks or 4) + 1)
            ],
        }
    return Material.model_validate(data)
