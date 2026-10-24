"""JARVIS planner, percentage comparison and Telegram contract (no network)."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from ezo_api.jarvis.percentages import compare, extract_percentages, report_markdown
from ezo_api.jarvis.planner import PlanError, plan_document_workflow
from ezo_api.jarvis.telegram import TelegramClient, TelegramError

REFERENCE = (
    "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, foiz ko'rsatkichlarini "
    "undan oldingi faylga o'xshatib tayyorla va Telegram'da Baxtiyorga yubor."
)
TOKEN = "123456:SECRET-test-token"


def test_reference_scenario_plan() -> None:
    plan = plan_document_workflow(REFERENCE)
    assert plan.to_dict() == {
        "root": "downloads",
        "compare_previous": True,
        "convert_pdf": True,
        "percentages": True,
        "recipient": "Baxtiyor",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Downloads'dagi eng oxirgi faylni PDF qil", {"convert_pdf": True, "recipient": None}),
        (
            "Convert the latest file in Downloads to PDF and send it to Dilnoza on Telegram",
            {"convert_pdf": True, "recipient": "Dilnoza"},
        ),
    ],
)
def test_plan_variants(text: str, expected: dict[str, object]) -> None:
    plan = plan_document_workflow(text).to_dict()
    assert {k: plan[k] for k in expected} == expected


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Ish stolidagi faylni o'chir", "unsupported_request"),  # no Downloads
        ("Downloads papkasini ko'rsat", "unsupported_request"),  # no file chosen
        ("Downloads eng oxirgi faylni Telegram'da yubor", "recipient_unclear"),
        ("Downloads eng oxirgi faylning foizlarini hisobla", "unsupported_request"),
        ("rm -rf / Downloads eng oxirgi", "unsupported_request"),
    ],
)
def test_planner_refuses_instead_of_guessing(text: str, code: str) -> None:
    with pytest.raises(PlanError) as caught:
        plan_document_workflow(text)
    assert caught.value.code == code


PREVIOUS = """Hisobot: sentyabr
Ishsizlik darajasi: 12,5%
Inflyatsiya — 9.8 %
Eksport ulushi 41%
"""
CURRENT = """Hisobot: oktyabr
Inflyatsiya: 10.1%
Ishsizlik darajasi 11%
Yangi ko'rsatkich: 3,25%
"""


def test_percentages_follow_the_previous_file_exactly() -> None:
    assert [p.value for p in extract_percentages(PREVIOUS)] == [
        Decimal("12.5"),
        Decimal("9.8"),
        Decimal("41"),
    ]
    comparison = compare(PREVIOUS, CURRENT)
    rows = {r.label: (r.previous, r.current, r.change_pp) for r in comparison.rows}
    assert rows["Ishsizlik darajasi"] == (Decimal("12.5"), Decimal("11"), Decimal("-1.5"))
    assert rows["Inflyatsiya"] == (Decimal("9.8"), Decimal("10.1"), Decimal("0.3"))
    assert rows["Eksport ulushi"][1] is None  # missing in the new file: never invented
    assert [p.label for p in comparison.only_in_current] == ["Yangi ko'rsatkich"]
    markdown = report_markdown(comparison, "sentyabr.txt", "oktyabr.txt")
    assert "| Ishsizlik darajasi | 12.5 | 11 | -1.5 |" in markdown
    assert "| Inflyatsiya | 9.8 | 10.1 | +0.3 |" in markdown
    assert "Yangi faylda topilmadi: Eksport ulushi" in markdown


def _client(handler) -> TelegramClient:  # type: ignore[no-untyped-def]
    return TelegramClient(TOKEN, transport=httpx.MockTransport(handler))


async def test_delivery_is_recorded_only_with_telegrams_message_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 77,
                    "date": 1761300000,
                    "chat": {"id": 555, "type": "private"},
                    "document": {"file_name": "a.pdf"},
                },
            },
        )

    receipt = await _client(handler).send_document("555", b"%PDF-1.7 x", "a.pdf", "EZO")
    assert receipt.message_id == 77 and receipt.chat_id == "555"
    assert seen[0].url.path == f"/bot{TOKEN}/sendDocument"


@pytest.mark.parametrize(
    ("response", "code", "unknown"),
    [
        (
            httpx.Response(200, json={"ok": False, "description": "chat not found"}),
            "rejected",
            False,
        ),
        (
            httpx.Response(403, json={"ok": False, "description": "bot was blocked"}),
            "rejected",
            False,
        ),
        (
            httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 9}}}),
            "unverified",
            True,
        ),
        (httpx.Response(502, text="<html>bad gateway</html>"), "bad_response", True),
    ],
)
async def test_unconfirmed_deliveries_are_failures(
    response: httpx.Response, code: str, unknown: bool
) -> None:
    with pytest.raises(TelegramError) as caught:
        await _client(lambda request: response).send_document("555", b"%PDF-", "a.pdf", "")
    assert caught.value.code == code and caught.value.outcome_unknown is unknown
    assert TOKEN not in caught.value.message


async def test_timeout_on_send_is_outcome_unknown_and_token_never_leaks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(TelegramError) as caught:
        await _client(handler).send_document("555", b"%PDF-", "a.pdf", "")
    assert caught.value.outcome_unknown is True and TOKEN not in str(caught.value)


async def test_recipient_is_found_only_by_exact_start_code_in_a_private_chat() -> None:
    updates = [
        {"message": {"text": "/start abc", "chat": {"id": 1, "type": "group"}}},
        {"message": {"text": "/start other", "chat": {"id": 2, "type": "private"}}},
        {
            "message": {
                "text": "/start abc",
                "chat": {"id": 3, "type": "private"},
                "from": {"first_name": "Baxtiyor", "last_name": "K"},
            }
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"ok": True, "result": updates}))

    found = await _client(handler).find_start("abc")
    assert found is not None and found.chat_id == "3" and found.name == "Baxtiyor K"
    assert await _client(handler).find_start("zzz") is None
