"""Ready-made sets of official documents an office needs from day one.

Every LEX.UZ number below was checked on lex.uz on 2026-11-19 (title search, then the document
page). EZO re-reads each act from LEX.UZ when it synchronizes the set; nothing here is legal
text, only the numbers and the titles they had on that day.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectionItem:
    source_doc_id: str
    title: str


@dataclass(frozen=True, slots=True)
class Collection:
    key: str
    connector: str
    language: str
    names: dict[str, str]
    items: tuple[CollectionItem, ...]


HOKIMIYAT = Collection(
    key="hokimiyat",
    connector="lexuz",
    language="uz",
    names={
        "uz": "Hokimiyat xodimi uchun asosiy hujjatlar",
        "en": "Core acts for a district administration (hokimiyat)",
        "ru": "Основные акты для хокимията",
    },
    items=(
        CollectionItem("6445145", "Ўзбекистон Республикаси Конституцияси"),
        CollectionItem("112170", "Маҳаллий давлат ҳокимияти тўғрисида"),
        CollectionItem("2509996", "Жисмоний ва юридик шахсларнинг мурожаатлари тўғрисида"),
        CollectionItem("5378966", "Норматив-ҳуқуқий ҳужжатлар тўғрисида"),
        CollectionItem("3492199", "Маъмурий тартиб-таомиллар тўғрисида"),
        CollectionItem("6145972", "Давлат фуқаролик хизмати тўғрисида"),
        CollectionItem("3088008", "Коррупцияга қарши курашиш тўғрисида"),
        CollectionItem("6257288", "Ўзбекистон Республикасининг Меҳнат кодекси"),
        CollectionItem(
            "97664", "Ўзбекистон Республикасининг Маъмурий жавобгарлик тўғрисидаги кодекси"
        ),
        CollectionItem("2304138", "Ўзбекистон Республикасининг Бюджет кодекси"),
        CollectionItem("152653", "Ўзбекистон Республикасининг Ер кодекси"),
        CollectionItem("4674902", "Ўзбекистон Республикасининг Солиқ кодекси"),
    ),
)

COLLECTIONS: dict[str, Collection] = {HOKIMIYAT.key: HOKIMIYAT}
