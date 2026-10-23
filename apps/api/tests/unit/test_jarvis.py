"""Unit and integration tests for EZO JARVIS Mode and OpenJarvis Companion.

Verifies end-to-end task planning, sandbox isolation, percentage arithmetic,
Telegram authorization gate, vector PDF generation, and Uzbek voice reporting.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from ezo_api.jarvis.companion import CompanionSecurityError, OpenJarvisCompanion
from ezo_api.jarvis.orchestrator import JarvisOrchestrator
from ezo_api.jarvis.pdf_worker import build_comparison_pdf
from ezo_api.jarvis.percentage_worker import compute_metric_percentages
from ezo_api.jarvis.schemas import JarvisStepStatus, JarvisStepType
from ezo_api.jarvis.telegram import TelegramAuthorizationError, TelegramDispatcher, resolve_contact


def test_companion_sandboxing_and_listing(tmp_path: Path) -> None:
    companion = OpenJarvisCompanion(root_dir=tmp_path)
    info = companion.get_device_info()
    assert info.pairing_status == "paired"
    assert info.online is True
    assert "Downloads" in info.authorized_directories

    # Seed reference fixtures
    fixtures = companion.seed_reference_fixtures()
    assert Path(fixtures["older_file"]).exists()
    assert Path(fixtures["newer_file"]).exists()

    files = companion.list_files("Downloads")
    assert len(files) == 2
    # Verify newest file is first
    assert files[0].filename == "metrics_2026_10_21.json"
    assert files[1].filename == "metrics_2026_10_20.json"
    assert files[0].sha256 != ""

    # Path traversal defense tests
    with pytest.raises(CompanionSecurityError):
        companion.list_files("../../etc")

    with pytest.raises(CompanionSecurityError):
        companion.read_file_content("Downloads", "../secret.txt")

    with pytest.raises(CompanionSecurityError):
        companion.read_file_content("UnauthorizedFolder", "test.txt")


def test_percentage_worker_arithmetic() -> None:
    older_data = {
        "korsatkichlar": {
            "oylik_faol_foydalanuvchilar": 10000,
            "yangi_mijozlar": 2000,
            "konversiya_foizi": 10.0,
        }
    }
    newer_data = {
        "korsatkichlar": {
            "oylik_faol_foydalanuvchilar": 12500,  # +25%
            "yangi_mijozlar": 2500,   # +25%
            "konversiya_foizi": 12.5,  # +2.5 foiz punkt
        }
    }

    result = compute_metric_percentages(older_data, newer_data)
    assert len(result.rows) == 3
    assert result.average_growth_percent == 25.0
    assert result.audit_hash != ""

    mau_row = next(r for r in result.rows if r.key == "oylik_faol_foydalanuvchilar")
    assert mau_row.percent_change == 25.0
    assert mau_row.trend == "osish"
    assert "+25.00%" in mau_row.formatted_change

    conv_row = next(r for r in result.rows if r.key == "konversiya_foizi")
    assert conv_row.is_percentage_point is True
    assert "foiz punkt" in conv_row.formatted_change


def test_pdf_generation_from_metrics(tmp_path: Path) -> None:
    older_data = {"metrics": {"foydalanuvchilar": 500}}
    newer_data = {"metrics": {"foydalanuvchilar": 650}}
    comparison = compute_metric_percentages(older_data, newer_data)

    out_file = tmp_path / "test_report.pdf"
    pdf_bytes, path = build_comparison_pdf(
        comparison=comparison,
        source_filename_older="older.json",
        source_filename_newer="newer.json",
        output_path=out_file,
    )
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")
    assert path.exists()


def test_telegram_dispatcher_approval_gate(tmp_path: Path) -> None:
    dispatcher = TelegramDispatcher()
    contact = resolve_contact("Baxtiyor")
    assert contact is not None
    assert contact.name == "Baxtiyor"

    dummy_pdf = tmp_path / "dummy.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy report content")

    draft = dispatcher.prepare_draft(
        recipient_query="Baxtiyor",
        attachment_path=dummy_pdf,
        summary_uz="O'sish sur'ati +15%",
    )
    assert draft.status == "awaiting_approval"
    assert draft.recipient.name == "Baxtiyor"

    # Reject without authorization
    with pytest.raises(TelegramAuthorizationError):
        dispatcher.send_message(draft.draft_id, user_authorized=False)

    # Re-prepare draft and authorize
    draft2 = dispatcher.prepare_draft(
        recipient_query="Baxtiyor",
        attachment_path=dummy_pdf,
        summary_uz="O'sish sur'ati +15%",
    )
    receipt = dispatcher.send_message(draft2.draft_id, user_authorized=True)
    assert receipt.status == "delivered"
    assert "Baxtiyor" in receipt.recipient_name
    assert receipt.audit_hash != ""


def test_jarvis_orchestrator_reference_acceptance_scenario(tmp_path: Path) -> None:
    companion = OpenJarvisCompanion(root_dir=tmp_path)
    companion.seed_reference_fixtures()

    orchestrator = JarvisOrchestrator(companion=companion)

    # Reference prompt in Uzbek:
    instruction = (
        "Downloads ichidagi eng oxirgi faylni och, PDF'ga aylantir, "
        "foiz ko'rsatkichlarini oldingi fayldagidek tayyorla va Telegram orqali Baxtiyorga yubor."
    )

    plan = orchestrator.plan_instruction(instruction, language="uz")
    assert len(plan.steps) == 8
    assert plan.status == "pending"

    # Execute plan until approval gate
    plan = orchestrator.execute_plan(plan.id)
    assert plan.status == "awaiting_approval"

    # Check steps 1 to 5 are COMPLETED
    assert plan.steps[0].status == JarvisStepStatus.COMPLETED  # list_files
    assert plan.steps[1].status == JarvisStepStatus.COMPLETED  # read_file
    assert plan.steps[2].status == JarvisStepStatus.COMPLETED  # compute_percentages
    assert plan.steps[3].status == JarvisStepStatus.COMPLETED  # generate_pdf
    assert plan.steps[4].status == JarvisStepStatus.COMPLETED  # prepare_telegram

    # Step 6 is awaiting approval
    assert plan.steps[5].type == JarvisStepType.REQUEST_APPROVAL
    assert plan.steps[5].status == JarvisStepStatus.AWAITING_APPROVAL

    # Submit explicit user approval
    plan = orchestrator.submit_approval(plan.id, approved=True)
    assert plan.status == "completed"

    # Check remaining steps completed
    assert plan.steps[5].status == JarvisStepStatus.COMPLETED
    assert plan.steps[6].status == JarvisStepStatus.COMPLETED  # send_telegram
    assert plan.steps[7].status == JarvisStepStatus.COMPLETED  # report_voice

    voice_res = plan.steps[7].result
    assert voice_res is not None
    assert "Topshiriq muvaffaqiyatli bajarildi" in voice_res["voice_script_uz"]
    assert "Telegram orqali Baxtiyorga yuborildi" in voice_res["voice_script_uz"]
