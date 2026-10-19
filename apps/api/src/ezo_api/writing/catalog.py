"""The document types EZO drafts professionally, with the fields and sections each needs.

Data only: detection, validation, blank templates and layout all read from here, so a
new type is one entry. Field keys are stable English identifiers; labels are Uzbek
because placeholders appear in the document (e.g. "[Qabul qiluvchi]").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Layout = Literal["letter", "act", "minutes", "plain", "speech", "cv", "academic"]


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    label: str
    """Uzbek label used for placeholders: [label]."""
    required: bool = True


@dataclass(frozen=True, slots=True)
class DocType:
    key: str
    names: dict[str, str]
    patterns: tuple[str, ...]
    layout: Layout
    mode: str
    """Default writing mode (see style.MODES)."""
    fields: tuple[Field, ...]
    sections: tuple[str, ...]
    """Ordered body parts the draft must contain (Uzbek headings or roles)."""
    draft: bool = True
    """Official/administrative paper: marked as a draft until a person approves it."""
    words: tuple[int, int] = (120, 450)

    def matcher(self) -> re.Pattern[str]:
        return re.compile("|".join(rf"(?<!\w){p}" for p in self.patterns))

    def required(self) -> list[Field]:
        return [f for f in self.fields if f.required]


# Common field sets ----------------------------------------------------------------------

RECIPIENT = Field("recipient", "Qabul qiluvchi (lavozimi, F.I.Sh.)")
SENDER = Field("sender", "Yuboruvchi (lavozimi, F.I.Sh.)")
ORG = Field("organization", "Tashkilot nomi")
DATE = Field("date", "Sana", required=False)
NUMBER = Field("number", "Hujjat raqami", required=False)
SUBJECT = Field("subject", "Mavzu")
SIGNATORY = Field("signatory", "Imzolovchi (lavozimi, F.I.Sh.)")
APPLICANT = Field("applicant", "Ariza beruvchi (F.I.Sh., manzili, telefoni)")
PLACE = Field("place", "Joy (shahar/tuman)", required=False)

LETTER = (ORG, NUMBER, DATE, RECIPIENT, SUBJECT, SIGNATORY)

CATALOG: tuple[DocType, ...] = (
    DocType(
        "ariza",
        {"uz": "Ariza", "ru": "Заявление", "en": "Application"},
        (r"ariza\w*", r"заявлени\w*", r"application letter", r"ариза\w*"),
        "letter",
        "official",
        (RECIPIENT, APPLICANT, DATE),
        ("so'rov mazmuni", "asos (agar bo'lsa)", "ilova (agar bo'lsa)"),
        words=(60, 250),
    ),
    DocType(
        "tushuntirish_xati",
        {"uz": "Tushuntirish xati", "ru": "Объяснительная записка", "en": "Explanatory note"},
        (r"tushuntirish xat\w*", r"объяснительн\w*", r"explanatory note", r"тушунтириш хат\w*"),
        "letter",
        "official",
        (RECIPIENT, SENDER, DATE, Field("event", "Holat (nima, qachon)")),
        ("holat bayoni", "sabablar", "xulosa"),
        words=(80, 350),
    ),
    DocType(
        "bildirishnoma",
        {"uz": "Bildirishnoma", "ru": "Уведомление", "en": "Notification"},
        (r"bildirishnoma\w*", r"уведомлени\w*", r"notification letter", r"билдиришнома\w*"),
        "letter",
        "official",
        (*LETTER,),
        ("xabar mazmuni", "muddat (agar bo'lsa)"),
        words=(60, 300),
    ),
    DocType(
        "xizmat_xati",
        {"uz": "Xizmat xati", "ru": "Служебное письмо", "en": "Official letter"},
        (r"xizmat xat\w*", r"служебн\w* (письм|записк)\w*", r"official letter", r"хизмат хат\w*"),
        "letter",
        "official",
        LETTER,
        ("kirish (asos)", "asosiy mazmun", "so'rov yoki taklif"),
        words=(100, 450),
    ),
    DocType(
        "rasmiy_murojaat",
        {"uz": "Rasmiy murojaat", "ru": "Официальное обращение", "en": "Official appeal"},
        (
            r"rasmiy murojaat\w*",
            r"murojaatnoma\w*",
            r"официальн\w* обращени\w*",
            r"official appeal",
            r"расмий мурожаат\w*",
        ),
        "letter",
        "official",
        LETTER,
        ("murojaat sababi", "asosiy mazmun", "so'rov"),
        words=(100, 500),
    ),
    DocType(
        "javob_xati",
        {"uz": "Javob xati", "ru": "Ответное письмо", "en": "Reply letter"},
        (r"javob xat\w*", r"ответн\w* письм\w*", r"reply letter", r"жавоб хат\w*"),
        "letter",
        "official",
        (*LETTER, Field("reference", "Javob berilayotgan xat (raqami, sanasi)")),
        ("murojaatga havola", "javob mazmuni", "xulosa"),
        words=(100, 450),
    ),
    DocType(
        "malumotnoma",
        {
            "uz": "Ma'lumotnoma loyihasi",
            "ru": "Справка (проект)",
            "en": "Certificate of information (draft)",
        },
        (r"ma'lumotnoma\w*", r"справк\w*", r"маълумотнома\w*"),
        "letter",
        "official",
        (ORG, NUMBER, DATE, Field("person", "Kim haqida (F.I.Sh.)"), SIGNATORY),
        ("tasdiqlanayotgan ma'lumot", "qayerga taqdim etish uchun"),
        words=(40, 200),
    ),
    DocType(
        "tavsiyanoma",
        {"uz": "Tavsiyanoma", "ru": "Рекомендательное письмо", "en": "Recommendation letter"},
        (
            r"tavsiyanoma\w*",
            r"tavsiya xat\w*",
            r"рекомендательн\w*",
            r"recommendation letter",
            r"letter of recommendation",
            r"тавсиянома\w*",
        ),
        "letter",
        "formal_letter",
        (
            Field("person", "Tavsiya etilayotgan shaxs (F.I.Sh.)"),
            SIGNATORY,
            DATE,
            Field("relationship", "Tanishlik asosi (qayerda, qancha muddat)"),
        ),
        ("tanishlik", "fazilatlar va yutuqlar (faqat berilgan faktlar)", "tavsiya"),
        draft=False,
        words=(150, 450),
    ),
    DocType(
        "taqdimnoma",
        {"uz": "Taqdimnoma", "ru": "Представление", "en": "Nomination"},
        (
            r"taqdimnoma\w*",
            r"представлени\w* (к|на) награ\w*",
            r"nomination letter",
            r"тақдимнома\w*",
        ),
        "letter",
        "official",
        (
            RECIPIENT,
            Field("person", "Taqdim etilayotgan shaxs (F.I.Sh., lavozimi)"),
            SIGNATORY,
            DATE,
        ),
        ("shaxs haqida", "mehnat faoliyati (berilgan faktlar)", "taqdimot maqsadi"),
        words=(150, 500),
    ),
    DocType(
        "dalolatnoma",
        {"uz": "Dalolatnoma", "ru": "Акт", "en": "Statement of record (act)"},
        (r"dalolatnoma\w*", r"\bакт\b", r"акт (приема|осмотра|проверки)\w*", r"далолатнома\w*"),
        "act",
        "official",
        (ORG, NUMBER, DATE, PLACE, Field("members", "Komissiya a'zolari (F.I.Sh., lavozimi)")),
        ("asos", "aniqlangan holat", "xulosa", "imzolar"),
        words=(120, 450),
    ),
    DocType(
        "bayonnoma",
        {"uz": "Bayonnoma", "ru": "Протокол", "en": "Minutes"},
        (r"bayonnoma\w*", r"протокол\w*", r"minutes of", r"meeting minutes", r"баённома\w*"),
        "minutes",
        "official",
        (
            ORG,
            NUMBER,
            DATE,
            PLACE,
            Field("chair", "Rais"),
            Field("secretary", "Kotib"),
            Field("attendees", "Qatnashchilar"),
        ),
        ("kun tartibi", "eshitildi", "so'zga chiqdilar", "qaror qilindi (taklif etilgan qarorlar)"),
        words=(200, 900),
    ),
    DocType(
        "yigilish_protokoli",
        {"uz": "Yig'ilish protokoli", "ru": "Протокол собрания", "en": "Meeting protocol"},
        (
            r"yig'ilish protokol\w*",
            r"majlis bayonnoma\w*",
            r"протокол (собрания|совещания)\w*",
            r"йиғилиш протокол\w*",
        ),
        "minutes",
        "official",
        (
            ORG,
            NUMBER,
            DATE,
            PLACE,
            Field("chair", "Rais"),
            Field("secretary", "Kotib"),
            Field("attendees", "Qatnashchilar"),
        ),
        ("kun tartibi", "muhokama", "qarorlar (taklif)", "topshiriqlar (mas'ul, muddat)"),
        words=(200, 900),
    ),
    DocType(
        "buyruq",
        {"uz": "Buyruq loyihasi", "ru": "Проект приказа", "en": "Draft order"},
        (r"buyruq\w*", r"приказ\w*", r"draft order", r"буйруқ\w*"),
        "act",
        "legal_drafting",
        (ORG, NUMBER, DATE, PLACE, Field("basis", "Asos (normativ hujjat yoki holat)"), SIGNATORY),
        ("preambula (asos)", "buyuraman: bandlar", "nazorat"),
        words=(120, 600),
    ),
    DocType(
        "qaror",
        {"uz": "Qaror loyihasi", "ru": "Проект решения/постановления", "en": "Draft decision"},
        (
            r"qaror loyiha\w*",
            r"qaror\b(?! qilindi)",
            r"проект (решения|постановления)\w*",
            r"draft decision",
            r"қарор лойиҳа\w*",
        ),
        "act",
        "legal_drafting",
        (ORG, NUMBER, DATE, PLACE, Field("basis", "Asos"), SIGNATORY),
        ("preambula", "qaror qiladi: bandlar", "ijro va nazorat"),
        words=(150, 800),
    ),
    DocType(
        "hisobot",
        {"uz": "Hisobot", "ru": "Отчёт", "en": "Report"},
        (r"hisobot\w*", r"отч[её]т\w*", r"\breport\b", r"ҳисобот\w*"),
        "plain",
        "official",
        (ORG, Field("period", "Hisobot davri"), SIGNATORY),
        (
            "kirish",
            "bajarilgan ishlar (faqat berilgan ma'lumotlar)",
            "ko'rsatkichlar",
            "muammolar",
            "takliflar",
        ),
        words=(300, 1500),
    ),
    DocType(
        "ish_rejasi",
        {"uz": "Ish rejasi", "ru": "План работы", "en": "Work plan"},
        (r"ish reja\w*", r"план работ\w*", r"work plan", r"иш режа\w*"),
        "plain",
        "concise",
        (ORG, Field("period", "Reja davri")),
        ("maqsad", "tadbirlar jadvali (tadbir, muddat, mas'ul)"),
        words=(150, 800),
    ),
    DocType(
        "xulosa",
        {"uz": "Xulosa", "ru": "Заключение", "en": "Conclusion / expert opinion"},
        (r"xulosa (yoz|tayyorla)\w*", r"заключени\w*", r"expert opinion", r"хулоса\w*"),
        "plain",
        "official",
        (Field("object", "Nima bo'yicha xulosa"), SIGNATORY, DATE),
        ("o'rganilgan hujjatlar", "tahlil", "xulosa"),
        words=(150, 700),
    ),
    DocType(
        "taklif_xati",
        {"uz": "Taklif xati", "ru": "Коммерческое предложение", "en": "Proposal letter"},
        (
            r"taklif xat\w*",
            r"коммерческ\w* предложени\w*",
            r"proposal letter",
            r"business proposal",
            r"таклиф хат\w*",
        ),
        "letter",
        "business",
        LETTER,
        ("taklif mohiyati", "afzalliklar", "shartlar", "keyingi qadam"),
        draft=False,
        words=(150, 500),
    ),
    DocType(
        "taklifnoma",
        {"uz": "Taklifnoma", "ru": "Приглашение", "en": "Invitation"},
        (r"taklifnoma\w*", r"приглашени\w*", r"invitation", r"таклифнома\w*"),
        "plain",
        "formal_letter",
        (Field("event", "Tadbir nomi"), DATE, PLACE, Field("host", "Taklif qiluvchi")),
        ("murojaat", "tadbir haqida", "vaqt va joy", "taklif"),
        draft=False,
        words=(50, 200),
    ),
    DocType(
        "tabriknoma",
        {"uz": "Tabriknoma", "ru": "Поздравление", "en": "Greeting / congratulation"},
        (
            r"tabriknoma\w*",
            r"tabrik (xat|matn)\w*",
            r"поздравлени\w*",
            r"congratulation",
            r"табрикнома\w*",
        ),
        "plain",
        "friendly",
        (Field("addressee", "Kimga"), Field("occasion", "Munosabat"), Field("from", "Kimdan")),
        ("tabrik", "tilaklar"),
        draft=False,
        words=(50, 250),
    ),
    DocType(
        "maruza",
        {"uz": "Ma'ruza", "ru": "Доклад", "en": "Lecture / report talk"},
        (r"ma'ruza\w*", r"доклад\w*", r"\blecture\b", r"маъруза\w*"),
        "speech",
        "speech",
        (
            Field("topic", "Mavzu"),
            Field("audience", "Tinglovchilar"),
            Field("duration", "Davomiyligi", required=False),
        ),
        ("kirish", "asosiy qism", "xulosa"),
        draft=False,
        words=(400, 2500),
    ),
    DocType(
        "nutq",
        {"uz": "Nutq matni", "ru": "Текст выступления", "en": "Speech"},
        (r"nutq\w*", r"выступлени\w*", r"\bspeech\b", r"нутқ\w*"),
        "speech",
        "speech",
        (
            Field("occasion", "Munosabat"),
            Field("speaker", "So'zlovchi"),
            Field("audience", "Tinglovchilar"),
        ),
        ("murojaat", "asosiy fikrlar", "yakun"),
        draft=False,
        words=(200, 1200),
    ),
    DocType(
        "press_reliz",
        {"uz": "Press-reliz", "ru": "Пресс-релиз", "en": "Press release"},
        (r"press-? ?reliz\w*", r"пресс-? ?релиз\w*", r"press release", r"пресс-релиз\w*"),
        "plain",
        "journalistic",
        (
            ORG,
            DATE,
            PLACE,
            Field("event", "Voqea (nima bo'ldi)"),
            Field("contact", "Matbuot uchun aloqa"),
        ),
        ("sarlavha", "lid (asosiy fakt)", "tafsilotlar", "tashkilot haqida"),
        words=(150, 600),
    ),
    DocType(
        "elon",
        {"uz": "E'lon", "ru": "Объявление", "en": "Announcement"},
        (r"e'lon\w*", r"объявлени\w*", r"announcement", r"эълон\w*"),
        "plain",
        "concise",
        (Field("subject", "Nima haqida"), DATE, PLACE, Field("contact", "Aloqa", required=False)),
        ("asosiy xabar", "tafsilotlar"),
        draft=False,
        words=(40, 250),
    ),
    DocType(
        "tadbir_dasturi",
        {"uz": "Tadbir dasturi", "ru": "Программа мероприятия", "en": "Event programme"},
        (
            r"tadbir dastur\w*",
            r"программ\w* мероприяти\w*",
            r"event program\w*",
            r"agenda for",
            r"тадбир дастур\w*",
        ),
        "plain",
        "concise",
        (Field("event", "Tadbir nomi"), DATE, PLACE),
        ("dastur jadvali (vaqt, tadbir, mas'ul)",),
        draft=False,
        words=(60, 400),
    ),
    DocType(
        "ishonchnoma",
        {
            "uz": "Ishonchnoma loyihasi",
            "ru": "Доверенность (проект)",
            "en": "Power of attorney (draft)",
        },
        (r"ishonchnoma\w*", r"доверенност\w*", r"power of attorney", r"ишончнома\w*"),
        "act",
        "legal_drafting",
        (
            Field("principal", "Ishonch bildiruvchi (F.I.Sh., pasport)"),
            Field("agent", "Vakil (F.I.Sh., pasport)"),
            Field("powers", "Vakolatlar"),
            Field("validity", "Amal qilish muddati"),
            DATE,
            PLACE,
        ),
        ("vakolatlar", "muddat", "imzolar"),
        words=(80, 400),
    ),
    DocType(
        "cv",
        {"uz": "Rezyume (CV)", "ru": "Резюме", "en": "CV / résumé"},
        (r"\bcv\b", r"rezyume\w*", r"резюме", r"r[eé]sum[eé]", r"curriculum vitae"),
        "cv",
        "concise",
        (
            Field("name", "F.I.Sh."),
            Field("contact", "Aloqa"),
            Field("experience", "Ish tajribasi"),
            Field("education", "Ma'lumoti"),
        ),
        ("qisqacha", "tajriba", "ma'lumot", "ko'nikmalar", "tillar"),
        draft=False,
        words=(150, 700),
    ),
    DocType(
        "motivatsion_xat",
        {"uz": "Motivatsion xat", "ru": "Мотивационное письмо", "en": "Motivation letter"},
        (r"motivats\w* xat\w*", r"мотивационн\w*", r"motivation letter", r"statement of purpose"),
        "plain",
        "formal_letter",
        (
            Field("name", "F.I.Sh."),
            Field("program", "Dastur / tashkilot"),
            Field("background", "Tajriba va yutuqlar (faktlar)"),
        ),
        ("kirish", "nima uchun bu dastur", "tajriba va yutuqlar", "maqsadlar", "yakun"),
        draft=False,
        words=(350, 900),
    ),
    DocType(
        "cover_letter",
        {
            "uz": "Kuzatuv xati (cover letter)",
            "ru": "Сопроводительное письмо",
            "en": "Cover letter",
        },
        (r"cover letter", r"сопроводительн\w* письм\w*", r"kuzatuv xat\w*"),
        "letter",
        "formal_letter",
        (
            Field("name", "F.I.Sh."),
            Field("position", "Lavozim"),
            Field("company", "Kompaniya"),
            Field("background", "Tajriba (faktlar)"),
        ),
        ("kirish", "mos tajriba", "nima uchun bu kompaniya", "yakun"),
        draft=False,
        words=(200, 450),
    ),
    DocType(
        "tadqiqot_taklifi",
        {"uz": "Ilmiy tadqiqot taklifi", "ru": "Заявка на исследование", "en": "Research proposal"},
        (
            r"tadqiqot (taklif|loyiha|rejas)\w*",
            r"research proposal",
            r"исследовательск\w* (заявк|проект)\w*",
            r"ilmiy loyiha\w*",
        ),
        "academic",
        "academic",
        (
            Field("topic", "Mavzu"),
            Field("author", "Muallif"),
            Field("supervisor", "Ilmiy rahbar", required=False),
        ),
        (
            "dolzarbligi",
            "muammo va savollar",
            "maqsad va vazifalar",
            "adabiyotlar sharhi (manbalar bilan)",
            "metodologiya",
            "kutilayotgan natijalar (gipoteza sifatida)",
            "ish rejasi",
            "adabiyotlar",
        ),
        draft=False,
        words=(600, 2500),
    ),
)

BY_KEY = {doc.key: doc for doc in CATALOG}
_MATCHERS = [(doc, doc.matcher()) for doc in CATALOG]


def detect(norm: str) -> DocType | None:
    """The document type named in a (normalized) request; the earliest mention wins."""
    best: tuple[int, DocType] | None = None
    for doc, pattern in _MATCHERS:
        match = pattern.search(norm)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), doc)
    return best[1] if best else None


def describe() -> list[dict[str, object]]:
    return [
        {
            "key": d.key,
            "names": d.names,
            "layout": d.layout,
            "mode": d.mode,
            "draft": d.draft,
            "fields": [{"key": f.key, "label": f.label, "required": f.required} for f in d.fields],
            "sections": list(d.sections),
        }
        for d in CATALOG
    ]


_WRITE_VERB = re.compile(
    r"(?<!\w)(yoz|yozib|yozing|tayyorla|tuz|tuzib|qoralama|shablon|namuna|loyiha|"
    r"draft|write|prepare|compose|template|напиши|подготов|составь|шаблон|образец|"
    r"ёз|тайёрла)"
)
_TEMPLATE = re.compile(r"(?<!\w)(shablon|namuna|blank|template|бланк|шаблон|образец)\w*")


def wants_writing(norm: str) -> DocType | None:
    """The document type when the (normalized) request asks EZO to write one."""
    doc = detect(norm)
    return doc if doc is not None and _WRITE_VERB.search(norm) else None


def wants_template(norm: str) -> bool:
    """An empty template is asked for ("xizmat xati shabloni", "blank ber"); "blankasida" /
    "на бланке" means *on the organization's letterhead*, with content."""
    for match in _TEMPLATE.finditer(norm):
        word = match.group(0)
        if word.startswith(("blank", "бланк")) and word.endswith(("da", "да", "е")):
            continue
        return True
    return False
