"""`python -m ezo_api.doctor` tells the owner exactly what is wrong, without printing keys."""

from ezo_api.doctor import run
from ezo_api.providers.errors import ProviderErrorKind
from tests.conftest import make_settings
from tests.fakes import FakeProvider


async def test_a_rejected_wrongly_shaped_gemini_key_is_named(database_url: str) -> None:
    secret = "AQ.Ab8RN6-not-a-real-key-0000000000000000000000000"
    settings = make_settings(database_url, GEMINI_API_KEY=secret)
    gemini = FakeProvider(name="gemini", fail_with=ProviderErrorKind.AUTH)
    lines, healthy = await run(settings, "uz", providers={"gemini": gemini})
    report = "\n".join(lines)
    assert healthy is False
    assert f"Google Gemini: bor ({len(secret)} belgi)" in report
    assert "«AIza» bilan boshlanadi" in report
    assert "KALIT RAD ETILDI" in report
    assert "o‘zbekcha server ovozi: o‘chiq" in report
    assert "--force-recreate api" in report
    assert "hujjat ishchisi): o‘chiq (yoqish: .env ga COMPOSE_PROFILES=documents" in report
    assert secret not in report and secret[:8] not in report


async def test_no_key_at_all_points_at_the_env_file(database_url: str) -> None:
    lines, healthy = await run(make_settings(database_url), "uz", providers={})
    report = "\n".join(lines)
    assert healthy is False
    assert ".env.txt yoki .env.example emas" in report
    assert "oflayn rejimda" in report


async def test_a_working_key_is_reported_working(database_url: str) -> None:
    settings = make_settings(
        database_url, GEMINI_API_KEY="AIza" + "x" * 35, EZO_DOCUMENT_WORKER="documents"
    )
    lines, healthy = await run(settings, "en", providers={"gemini": FakeProvider(name="gemini")})
    assert healthy is True
    assert "  Google Gemini: works" in lines
    assert any(
        line.startswith("  Reading PDF/DOCX/EPUB/scans (document worker): on") for line in lines
    )
