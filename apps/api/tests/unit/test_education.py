"""Education materials without a model: recognising requests, EZO's checks (answer key,
timing, weights, points) and rendering to Word Markdown, Excel sheets and slides."""

from __future__ import annotations

from ezo_api.documents.markdown_io import parse_markdown
from ezo_api.education.catalog import BY_KEY, Options, options_from, wants_education
from ezo_api.education.models import Material, build_prompt, check, parse
from ezo_api.education.render import blank, to_deck, to_markdown, to_sheets


def test_requests() -> None:
    cases = {
        "7-sinf uchun fotosintez mavzusida 45 daqiqalik dars ishlanmasi tayyorla": "lesson",
        "Составь план урока по математике на 80 минут": "lesson",
        "Shu ma'ruzadan 10 ta test tuz": "quiz",
        "Prepare 15 practice questions on photosynthesis": "quiz",
        "Iqtisodiyot fanidan sillabus tuz": "syllabus",
        "Baholash mezonlarini tuz": "rubric",
        "IELTSga 6 haftalik tayyorgarlik rejasini tuz": "study_plan",
        "Ўқувчилар учун тест тузиб бер": "quiz",
        "45 daqiqalik dars ishlanmasi shablonini ber": "lesson",
    }
    for text, key in cases.items():
        kind = wants_education(text)
        assert kind is not None and kind.key == key, text
    for text in (
        "Bu funksiya uchun test yoz",
        "test natijalari qanday?",
        "Dars qachon boshlanadi?",
    ):
        assert wants_education(text) is None, text
    options = options_from("1-kurs uchun 2 para dars, 12 ta savol, taqdimot bilan")
    assert (options.minutes, options.questions, options.level, options.slides) == (
        160,
        12,
        "1-kurs",
        True,
    )
    assert options_from("8 haftalik reja, kuniga 1 soat").weeks == 8


QUIZ = {
    "title": "Fotosintez",
    "questions": [
        {
            "question": "Fotosintez qayerda boradi?",
            "options": ["Xloroplast", "Mitoxondriya", "Yadro", "Ribosoma"],
            "correct": 0,
            "explanation": "Xlorofill xloroplastda joylashgan.",
        },
        {"type": "true_false", "question": "Fotosintezda kislorod ajraladi.", "correct": 0},
        {"question": "Buzilgan savol", "options": ["Bir", "Ikki"], "correct": 5},
        {"type": "open", "question": "Fotosintez tenglamasini yozing."},
    ],
}


def test_quiz_checks_and_answer_key() -> None:
    material = parse(QUIZ)
    assert material is not None
    report = check(BY_KEY["quiz"], material, Options(questions=5))
    assert report.answer_key == [(1, "A"), (2, "A"), (3, "?"), (4, "—")]
    assert report.issues == [
        "Question 3: no valid correct answer",
        "Question 4: no model answer",
        "4 questions instead of 5",
    ]
    assert material.questions[1].options == ["To'g'ri", "Noto'g'ri"]
    markdown = to_markdown(BY_KEY["quiz"], material, report, "uz")
    assert "**1. Fotosintez qayerda boradi?**" in markdown and "- A) Xloroplast" in markdown
    key_section = markdown.split("## Javoblar kaliti (o'qituvchi uchun)")[1]
    assert "| 1 | A | Xlorofill xloroplastda joylashgan. |" in key_section
    spec = parse_markdown(markdown)  # renders through EZO's document pipeline
    assert spec.title == "Fotosintez"
    [sheet] = to_sheets(BY_KEY["quiz"], material, report, "uz")
    assert sheet["columns"][:3] == ["№", "Savol", "A"]
    assert sheet["rows"][0][:3] == [1, "Fotosintez qayerda boradi?", "Xloroplast"]
    assert sheet["rows"][0][6] == "A"


def test_lesson_timing_rubric_and_slides() -> None:
    material = Material.model_validate(
        {
            "title": "Fotosintez",
            "subject": "Biologiya",
            "level": "7-sinf",
            "duration_minutes": 45,
            "stages": [
                {"name": "Kirish", "minutes": 5},
                {"name": "Yangi mavzu", "minutes": 20},
                {"name": "Mashq", "minutes": 15},
            ],
            "criteria": [
                {
                    "criterion": "Tushunish",
                    "levels": [{"label": "A'lo", "points": 5}, {"label": "Yaxshi", "points": 4}],
                },
                {
                    "criterion": "Amaliyot",
                    "levels": [{"label": "Past", "points": 2}, {"label": "Yuqori", "points": 5}],
                },
            ],
            "slides": [{"title": "Fotosintez nima?", "bullets": ["Yorug'lik", "Xlorofill"]}],
        }
    )
    report = check(BY_KEY["lesson"], material, Options(minutes=45))
    assert report.total_minutes == 40 and report.max_points == 10
    assert report.issues == [
        "The stages add up to 40 minutes, not 45",
        "“Amaliyot”: levels are not ordered by points",
    ]
    markdown = to_markdown(BY_KEY["lesson"], material, report, "uz")
    assert "| **Jami** | 40 |" in markdown and "**Maksimal ball: 10**" in markdown
    names = [s["name"] for s in to_sheets(BY_KEY["lesson"], material, report, "uz")]
    assert names == ["Dars bosqichlari", "Baholash mezonlari"]
    deck = to_deck(material, "uz")
    assert deck is not None and [s["layout"] for s in deck["slides"]] == ["title", "bullets"]


def test_syllabus_and_study_plan_checks() -> None:
    syllabus = Material.model_validate(
        {
            "weeks": [{"week": 1, "topic": "Kirish"}, {"week": 3, "topic": "Bozor"}],
            "assessment": [
                {"component": "Joriy", "weight": 40},
                {"component": "Yakuniy", "weight": 50},
            ],
        }
    )
    report = check(BY_KEY["syllabus"], syllabus, Options(weeks=2))
    assert report.issues == [
        "Assessment weights add up to 90 %, not 100 %",
        "Weeks are not numbered 1, 2, 3… without gaps",
    ]
    sessions = [
        {"day": "Du", "task": "Test", "minutes": 60},
        {"day": "Se", "task": "Lug'at", "minutes": 30},
    ]
    plan = Material.model_validate(
        {"plan": [{"week": 1, "focus": "Listening", "sessions": sessions}]}
    )
    report = check(BY_KEY["study_plan"], plan, Options(weeks=6))
    assert report.weekly_minutes == {1: 90} and report.issues == ["1 weeks instead of 6"]


def test_templates_and_prompt() -> None:
    lesson = blank(BY_KEY["lesson"], Options(minutes=80, level="1-kurs"), "uz")
    report = check(BY_KEY["lesson"], lesson, Options(minutes=80))
    assert report.total_minutes == 80 and report.issues == []
    assert lesson.level == "1-kurs" and "[" in lesson.stages[0].name
    quiz = blank(BY_KEY["quiz"], Options(questions=3), "ru")
    assert len(quiz.questions) == 3
    for key in ("syllabus", "rubric", "study_plan"):
        material = blank(BY_KEY[key], Options(), "en")
        assert to_markdown(BY_KEY[key], material, check(BY_KEY[key], material, Options()), "en")
    prompt = build_prompt(BY_KEY["quiz"], Options(questions=12), "Russian", "")
    assert "Exactly 12 questions" in prompt and "Never invent statistics" in prompt
    assert "Language: Russian" in prompt


def test_defense_questions_have_outlines_not_an_answer_key() -> None:
    kind = wants_education("Shu dissertatsiya bo'yicha himoya savollarini tuz")
    assert kind is not None and kind.key == "defense" and kind.outputs == ("docx",)
    material = Material.model_validate(
        {
            "title": "Himoyaga tayyorgarlik",
            "questions": [
                {
                    "type": "mcq",
                    "question": "Ilmiy yangilik nimada?",
                    "answer": "2-bobdagi modelni ayting",
                    "explanation": "Komissiya har doim so'raydi",
                }
            ],
        }
    )
    report = check(kind, material, Options())
    assert report.issues == [] and material.questions[0].type == "open"
    markdown = to_markdown(kind, material, report, "uz")
    assert "*Javob rejasi:* 2-bobdagi modelni ayting" in markdown
    assert "Javoblar kaliti" not in markdown
    assert "Exactly" not in build_prompt(kind, Options(), "Uzbek", "")
    assert "15 likely committee questions" in build_prompt(kind, Options(), "Uzbek", "")
