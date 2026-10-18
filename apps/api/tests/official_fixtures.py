"""Test pages for the official-source framework.

Honest labelling: LEX.UZ could not be reached from the build environment, so these
are NOT copies of live LEX.UZ pages. They are small synthetic HTML pages written for
the tests. The document number, date and LEX.UZ ID of law LRU-682 ("On normative
legal acts", 20.04.2021, lex.uz/docs/5695915) come from public search results; the
article texts below are short illustrative paraphrases, not official wording.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from ezo_api.knowledge.fetch import SafeFetcher

LRU_682 = "5695915"

UZ_LATIN = """<!doctype html><html lang="uz"><head><meta charset="utf-8">
<title>O‘RQ-682-son 20.04.2021. Normativ-huquqiy hujjatlar toʻgʻrisida</title></head>
<body><nav>Bosh sahifa | Qidiruv</nav><main><article>
<h1>Normativ-huquqiy hujjatlar toʻgʻrisida</h1>
<p>1-modda. Ushbu Qonunning maqsadi</p>
<p>Ushbu Qonunning maqsadi normativ-huquqiy hujjatlarni ishlab chiqish, qabul qilish va
eʼlon qilish sohasidagi munosabatlarni tartibga solishdan iborat (illustrative text).</p>
<p>2-modda. Normativ-huquqiy hujjatlarni rasmiy eʼlon qilish</p>
<p>Normativ-huquqiy hujjatlar Qonunchilik maʼlumotlari milliy bazasida rasmiy eʼlon
qilinadi (illustrative text).</p>
</article></main><footer>© LEX.UZ</footer></body></html>"""

UZ_CYRILLIC = """<!doctype html><html lang="uz"><head><meta charset="utf-8">
<title>ЎРҚ-682-сон 20.04.2021. Норматив-ҳуқуқий ҳужжатлар тўғрисида</title></head>
<body><main><article>
<p>1-модда. Ушбу Қонуннинг мақсади</p>
<p>Ушбу Қонуннинг мақсади норматив-ҳуқуқий ҳужжатларни ишлаб чиқиш, қабул қилиш ва эълон
қилиш соҳасидаги муносабатларни тартибга солишдан иборат (illustrative text).</p>
<p>2-модда. Норматив-ҳуқуқий ҳужжатларни расмий эълон қилиш</p>
<p>Норматив-ҳуқуқий ҳужжатлар Қонунчилик маълумотлари миллий базасида расмий эълон
қилинади (illustrative text).</p>
</article></main></body></html>"""

RUSSIAN = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>ЗРУ-682 от 20.04.2021 г. О нормативно-правовых актах</title></head>
<body><main><article>
<p>Статья 1. Цель настоящего Закона</p>
<p>Целью настоящего Закона является регулирование отношений в области разработки, принятия
и опубликования нормативно-правовых актов (illustrative text).</p>
<p>Статья 2. Официальное опубликование нормативно-правовых актов</p>
<p>Нормативно-правовые акты официально публикуются в Национальной базе данных
законодательства (illustrative text).</p>
</article></main></body></html>"""


def amended(page: str) -> str:
    """The same page with one more (illustrative) article: an amendment."""
    return page.replace(
        "</article>",
        "<p>3-modda. Yakuniy qoidalar</p><p>Ushbu Qonun rasmiy eʼlon qilingan kundan eʼtiboran "
        "kuchga kiradi (illustrative amendment).</p></article>",
    )


def with_status(page: str, label: str) -> str:
    return page.replace("<article>", f"<article><p>Holati: {label}</p>", 1)


Handler = Callable[[httpx.Request], httpx.Response]


def html(body: str, status: int = 200, **headers: str) -> httpx.Response:
    return httpx.Response(
        status, content=body.encode("utf-8"), headers={"content-type": "text/html", **headers}
    )


class FakeSite:
    """A scripted website: path → response (or callable), with a request log."""

    def __init__(self, robots: httpx.Response | None = None) -> None:
        self.routes: dict[str, httpx.Response | Callable[[], httpx.Response]] = {}
        self.robots = robots or httpx.Response(404)
        self.log: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.log.append(path)
        if path == "/robots.txt":
            return self.robots
        route = self.routes.get(path)
        if route is None:
            return httpx.Response(404)
        return route() if callable(route) else route

    def fetcher(self) -> SafeFetcher:
        async def resolve(host: str, port: int) -> list[str]:
            return ["93.184.216.34"]  # any public address; no real DNS in tests

        return SafeFetcher(transport=httpx.MockTransport(self.handler), resolver=resolve)


class Sleeps:
    """Records requested sleeps instead of sleeping, with a clock that only moves when
    something sleeps (so pacing checks do not depend on how fast the database is)."""

    def __init__(self) -> None:
        self.calls: list[float] = []
        self.now = 1_000.0

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.now += seconds

    def clock(self) -> float:
        return self.now
