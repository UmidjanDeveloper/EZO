"""A deck that uses every layout (shared by tests and visual checks)."""

from ezo_api.documents.render.spec import DeckSpec

SAMPLE_DECK = {
    "title": "Xatirchi tumani: raqamli xizmatlar 2026",
    "subtitle": "Hokimlik uchun loyiha taklifi",
    "author": "EZO",
    "language": "uz",
    "theme": "civic",
    "slides": [
        {
            "layout": "cover",
            "kicker": "Loyiha taklifi",
            "title": "Xatirchi tumani: raqamli xizmatlar 2026",
            "subtitle": "Davlat xizmatlarini aholiga yaqinlashtirish",
            "body": "Oktabr 2026",
        },
        {
            "layout": "title_subtitle",
            "title": "Bir oynada barcha xizmatlar",
            "subtitle": "Navbatsiz, qog‘ozsiz, shaffof",
        },
        {
            "layout": "section",
            "kicker": "01",
            "title": "Hozirgi holat",
            "subtitle": "Muammolar va imkoniyatlar",
        },
        {
            "layout": "problem_solution",
            "title": "Asosiy muammo va yechim",
            "columns": [
                {
                    "title": "Muammo",
                    "bullets": [
                        "Navbatlar 2–3 soat",
                        "Qog‘oz hujjatlar yo‘qoladi",
                        "Shaffoflik past",
                    ],
                },
                {
                    "title": "Yechim",
                    "bullets": ["Onlayn ariza", "Elektron arxiv", "Ochiq monitoring paneli"],
                },
            ],
        },
        {
            "layout": "big_number",
            "title": "Kutish vaqti",
            "metric": {"value": "−65%", "label": "o‘rtacha navbat vaqtining qisqarishi"},
            "body": "Pilot hududlar natijasi asosida baholangan",
        },
        {
            "layout": "kpi",
            "title": "Maqsadli ko‘rsatkichlar",
            "metrics": [
                {"value": "120", "label": "onlayn xizmat"},
                {"value": "85%", "label": "elektron arizalar ulushi"},
                {"value": "24/7", "label": "xizmat ko‘rsatish"},
            ],
        },
        {
            "layout": "chart",
            "title": "Arizalar soni (ming)",
            "chart": {
                "type": "column",
                "categories": ["2023", "2024", "2025", "2026"],
                "series": [
                    {"name": "Qog‘oz", "values": [42, 38, 25, 12]},
                    {"name": "Onlayn", "values": [8, 15, 31, 52]},
                ],
                "source": "Tuman hokimligi ma’lumotlari (taxminiy)",
            },
            "bullets": ["Onlayn ulush 4 yilda 6 barobar oshadi", "Qog‘oz arizalar keskin kamayadi"],
        },
        {
            "layout": "chart",
            "title": "Xarajatlar taqsimoti",
            "chart": {
                "type": "doughnut",
                "categories": ["Uskunalar", "Dasturiy ta’minot", "O‘qitish", "Qo‘llab-quvvatlash"],
                "series": [{"name": "Ulush", "values": [40, 30, 18, 12]}],
            },
        },
        {
            "layout": "chart",
            "title": "Foydalanuvchilar o‘sishi",
            "chart": {
                "type": "line",
                "categories": ["Yan", "Fev", "Mar", "Apr", "May", "Iyun"],
                "series": [{"name": "Faol", "values": [1.2, 2.5, 3.1, 4.8, 6.0, 7.4]}],
                "unit": "k",
            },
        },
        {
            "layout": "chart",
            "title": "Xizmatlar bo‘yicha talab",
            "chart": {
                "type": "bar",
                "categories": ["Ma’lumotnoma", "Ruxsatnoma", "Ro‘yxatga olish", "Subsidiya"],
                "series": [{"name": "Arizalar", "values": [5400, 3100, 2600, 900]}],
            },
        },
        {
            "layout": "table",
            "title": "Bosqichlar va mas’ullar",
            "table": {
                "headers": ["Bosqich", "Muddat", "Mas’ul", "Holat"],
                "rows": [
                    ["Tahlil", "Noyabr", "IT bo‘lim", "Boshlangan"],
                    ["Pilot", "Dekabr–Yanvar", "Hokimlik", "Rejada"],
                    ["Joriy etish", "Fevral–Aprel", "Pudratchi", "Rejada"],
                    ["Baholash", "May", "Monitoring", "Rejada"],
                ],
            },
        },
        {
            "layout": "timeline",
            "title": "Yo‘l xaritasi",
            "steps": [
                {"label": "2026 Q4", "text": "Tahlil va loyiha"},
                {"label": "2027 Q1", "text": "Pilot 3 mahallada"},
                {"label": "2027 Q2", "text": "Butun tuman"},
                {"label": "2027 Q3", "text": "Baholash va kengaytirish"},
            ],
        },
        {
            "layout": "process",
            "title": "Ariza qanday ishlaydi",
            "steps": [
                {"label": "Ariza", "text": "Fuqaro telefon orqali yuboradi"},
                {"label": "Tekshiruv", "text": "Mas’ul xodim 1 kunda ko‘radi"},
                {"label": "Qaror", "text": "Elektron imzo bilan"},
                {"label": "Natija", "text": "SMS va onlayn kabinet"},
            ],
        },
        {
            "layout": "roadmap",
            "title": "Joriy etish bosqichlari",
            "steps": [
                {"label": "Tayyorlov", "text": "Uskunalar, o‘qitish"},
                {"label": "Pilot", "text": "3 mahalla"},
                {"label": "Kengaytirish", "text": "Barcha mahallalar"},
                {"label": "Barqarorlik", "text": "Qo‘llab-quvvatlash"},
            ],
        },
        {
            "layout": "architecture",
            "title": "Tizim arxitekturasi",
            "nodes": [
                {"id": "u", "label": "Fuqaro ilovasi"},
                {"id": "g", "label": "API shlyuz"},
                {"id": "s", "label": "Xizmatlar"},
                {"id": "a", "label": "Elektron arxiv"},
                {"id": "m", "label": "Monitoring"},
            ],
            "edges": [["u", "g"], ["g", "s"], ["s", "a"], ["s", "m"]],
        },
        {
            "layout": "two_column",
            "title": "Kim nima oladi",
            "columns": [
                {"title": "Aholi", "bullets": ["Navbatsiz xizmat", "Shaffof muddatlar"]},
                {"title": "Hokimlik", "bullets": ["Real vaqt nazorati", "Kam xarajat"]},
            ],
        },
        {
            "layout": "three_column",
            "title": "Uch ustun",
            "columns": [
                {"title": "Odamlar", "bullets": ["O‘qitilgan xodimlar"]},
                {"title": "Jarayonlar", "bullets": ["Standart reglament"]},
                {"title": "Texnologiya", "bullets": ["Ishonchli platforma"]},
            ],
        },
        {
            "layout": "comparison",
            "title": "Ikki variant",
            "columns": [
                {"title": "O‘z serverimiz", "bullets": ["Nazorat yuqori", "Xarajat ko‘p"]},
                {"title": "Davlat bulut xizmati", "bullets": ["Tez joriy etiladi", "Xarajat kam"]},
            ],
        },
        {
            "layout": "before_after",
            "title": "Fuqaro tajribasi",
            "columns": [
                {"bullets": ["3 marta kelish", "Qog‘oz nusxalar"]},
                {"bullets": ["1 marta ariza", "Hammasi onlayn"]},
            ],
        },
        {
            "layout": "quote",
            "quote": "Xizmat odamga borishi kerak, odam xizmat ortidan yugurmasligi kerak.",
            "author": "Loyiha tamoyili",
        },
        {
            "layout": "hero_image",
            "title": "Mahalla markazlari",
            "body": "Har bir mahallada yordamchi xodim va terminal.",
            "image_prompt": "modern community service center",
        },
        {
            "layout": "market",
            "title": "Qamrov",
            "metrics": [
                {"value": "280 ming", "label": "tuman aholisi"},
                {"value": "95 ming", "label": "yillik arizachilar"},
                {"value": "60 ming", "label": "birinchi yil onlayn"},
            ],
        },
        {
            "layout": "product",
            "title": "Fuqaro kabineti",
            "bullets": ["Ariza holati real vaqtda", "Hujjatlar bir joyda", "O‘zbek va rus tilida"],
        },
        {
            "layout": "team",
            "title": "Loyiha jamoasi",
            "columns": [
                {"title": "Aziz Karimov", "bullets": ["Loyiha rahbari"]},
                {"title": "Dilnoza Rasulova", "bullets": ["Jarayonlar"]},
                {"title": "Sardor Aliyev", "bullets": ["Texnik rahbar"]},
            ],
        },
        {
            "layout": "financial",
            "title": "Byudjet (mln so‘m)",
            "chart": {
                "type": "column",
                "categories": ["2026", "2027", "2028"],
                "series": [{"name": "Xarajat", "values": [1200, 800, 400]}],
            },
            "metrics": [
                {"value": "2.4 mlrd", "label": "jami 3 yil"},
                {"value": "18 oy", "label": "qoplanish muddati"},
            ],
        },
        {
            "layout": "bullets",
            "title": "Xavflar va choralar",
            "bullets": [
                "Internet sifati — mobil zaxira kanal",
                "Xodimlar tayyorgarligi — o‘qitish dasturi",
                "Ma’lumot xavfsizligi — audit va shifrlash",
            ],
        },
        {
            "layout": "closing",
            "title": "Rahmat!",
            "subtitle": "Savollar va takliflar uchun ochiqmiz",
            "bullets": ["xatirchi.uz", "+998 66 000 00 00"],
        },
    ],
}


def sample_deck() -> DeckSpec:
    return DeckSpec.model_validate(SAMPLE_DECK)
