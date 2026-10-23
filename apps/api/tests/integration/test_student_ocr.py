"""Student scans/images: OCR choice, immutable storage, worker hand-off and outcomes.

The durable queue, DB transactions and publication are real; only the executor is a
test double here. Real OCR inside the isolated container is covered by
test_isolated_executor_container.py / test_student_executor.py (Docker, CI).
"""

import hashlib

import pytest
from sqlalchemy import select

from ezo_api.db.models import DocumentJob, DocumentRevision, KnowledgeChunk, KnowledgeDocument
from ezo_api.db.session import Database
from ezo_api.documents.executor.protocol import (
    OCR_LANGUAGES,
    ExtractionResult,
    OcrSummary,
    SourceSection,
)
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.student.ingestion import StudentIngestion
from ezo_api.student.worker import StudentWorker
from tests.integration.test_document_jobs import seed

PNG = b"\x89PNG\r\n\x1a\n" + b"scan-bytes"
JPEG = b"\xff\xd8\xff" + b"photo-bytes"
SCAN = b"%PDF-scanned-without-text-layer"
TEXT = "Ўзбекистон Республикаси\n\nFotosintez quyosh energiyasini saqlaydi."


@pytest.fixture
async def db(database_url):
    database = Database(database_url)
    yield database
    await database.dispose()


def ocr_result(data: bytes, *, status="completed") -> ExtractionResult:
    if status != "completed":
        return ExtractionResult(
            source_sha256=hashlib.sha256(data).hexdigest(),
            text="",
            sections=[],
            needs_ocr=True,
            ocr=OcrSummary(status=status, engine="tesseract 5", languages=["uzb_cyrl"], pages=9),
        )
    split = TEXT.index("\n")
    return ExtractionResult(
        source_sha256=hashlib.sha256(data).hexdigest(),
        text=TEXT,
        sections=[
            SourceSection(start=0, end=split, page=1),
            SourceSection(start=split + 2, end=len(TEXT), page=2),
        ],
        ocr=OcrSummary(
            status="completed",
            engine="tesseract 5.5.0",
            languages=["uzb", "uzb_cyrl"],
            pages=2,
            pages_read=2,
            mean_confidence=88.4,
            low_confidence_pages=[2],
        ),
    )


class Recorder:
    """Records what the worker asks the isolated executor to do."""

    def __init__(self, result=None) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.result = result

    def extract(self, data, format, *, ocr_languages=(), cancelled=None):
        self.calls.append((format, tuple(ocr_languages)))
        return self.result(data) if self.result else ocr_result(data)


async def test_upload_validates_format_signature_and_languages(client):
    def post(name, data, **params):
        return client.post(
            "/api/student/uploads", params={"filename": name, **params}, content=data
        )

    assert (await post("scan.png", PNG)).status_code == 201
    jpeg = await post("photo.JPG", JPEG)
    assert jpeg.status_code == 201
    no_ocr = await post("other.png", PNG + b"2", no_ocr="true")
    assert no_ocr.status_code == 422 and "OCR" in no_ocr.text
    assert (await post("fake.png", b"%PDF-not-a-png")).status_code == 422
    assert (await post("bad.pdf", SCAN, ocr=["deu"])).status_code == 422
    assert (await post("malware.exe", b"MZ")).status_code == 422


async def test_ocr_choice_is_stored_with_the_immutable_source(db):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    default = await jobs.submit_raw(scope.user, scope.project, "a.pdf", SCAN)
    narrowed = await jobs.submit_raw(
        scope.user, scope.project, "b.pdf", SCAN + b"b", ["rus", "eng"]
    )
    disabled = await jobs.submit_raw(scope.user, scope.project, "c.pdf", SCAN + b"c", [])
    image = await jobs.submit_raw(scope.user, scope.project, "d.jpeg", JPEG)
    async with db.sessionmaker() as session:
        meta = {
            job.id: (await session.get(DocumentRevision, job.input_revision_id)).meta
            for job in (default, narrowed, disabled, image)
        }
        doc = await session.get(KnowledgeDocument, image.document_id)
        assert doc.mime_type == "image/jpeg"
    assert meta[default.id]["ocr_languages"] == list(OCR_LANGUAGES)
    assert meta[narrowed.id]["ocr_languages"] == ["eng", "rus"]  # fixed order
    assert meta[disabled.id]["ocr_languages"] == []
    assert meta[image.id]["raw_format"] == "jpeg"


async def test_worker_passes_languages_and_publishes_ocr_provenance(db):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    job = await jobs.submit_raw(scope.user, scope.project, "scan.pdf", SCAN, ["uzb", "uzb_cyrl"])
    executor = Recorder()
    assert await StudentWorker(jobs, executor, "ocr-worker").process_one()
    assert executor.calls == [("pdf", ("uzb", "uzb_cyrl"))]
    done = await jobs.get(scope.user, scope.project, job.id)
    assert done.state == "completed"
    async with db.sessionmaker() as session:
        doc = await session.get(KnowledgeDocument, job.document_id)
        output = await session.get(DocumentRevision, doc.current_revision_id)
        assert output.raw_text == TEXT
        assert output.meta["ocr"]["status"] == "completed"
        assert output.meta["ocr"]["low_confidence_pages"] == [2]
        chunks = (
            await session.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.document_id == job.document_id)
            )
        ).all()
        assert chunks and all(c.meta["ocr"] is True for c in chunks)
        assert [c.meta["page_start"] for c in chunks] == [1, 2]
        for chunk in chunks:
            assert chunk.text == TEXT[chunk.meta["start"] : chunk.meta["end"]]


@pytest.mark.parametrize("status", ["page_limit", "deadline", "unavailable", "no_text"])
async def test_incomplete_ocr_fails_with_a_fixed_ocr_category(db, status):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    job = await jobs.submit_raw(scope.user, scope.project, "big.pdf", SCAN + status.encode())
    executor = Recorder(lambda data: ocr_result(data, status=status))
    assert await StudentWorker(jobs, executor, "ocr-worker").process_one()
    failed = await jobs.get(scope.user, scope.project, job.id)
    assert failed.state == "failed" and failed.error_code == "ocr_incomplete"
    assert failed.attempts == 1  # not retried automatically: the same limits would apply
    async with db.sessionmaker() as session:
        doc = await session.get(KnowledgeDocument, job.document_id)
        assert doc.current_revision_id is None


async def test_scan_without_ocr_can_be_retried_with_ocr(db):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    job = await jobs.submit_raw(scope.user, scope.project, "scan.pdf", SCAN, [])

    def no_text_layer(data):
        return ExtractionResult(
            source_sha256=hashlib.sha256(data).hexdigest(), text="", sections=[], needs_ocr=True
        )

    first = Recorder(no_text_layer)
    assert await StudentWorker(jobs, first, "w").process_one()
    assert first.calls == [("pdf", ())]
    failed = await jobs.get(scope.user, scope.project, job.id)
    assert failed.error_code == "ocr_required"
    with pytest.raises(JobError, match="Supported OCR languages"):
        await jobs.retry(scope.user, scope.project, job.id, ["klingon"])
    successor = await jobs.retry(scope.user, scope.project, job.id, ["rus"])
    again = await jobs.retry(scope.user, scope.project, job.id, ["rus"])
    assert again.id == successor.id
    second = Recorder()
    assert await StudentWorker(jobs, second, "w").process_one()
    assert second.calls == [("pdf", ("rus",))]
    assert (await jobs.get(scope.user, scope.project, successor.id)).state == "completed"
    async with db.sessionmaker() as session:
        # The original failed generation and its immutable choice are untouched.
        original = await session.get(DocumentRevision, job.input_revision_id)
        assert original.meta["ocr_languages"] == []
        assert (await session.get(DocumentJob, job.id)).state == "failed"


async def test_retry_keeps_the_previous_ocr_choice_by_default(db):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    job = await jobs.submit_raw(scope.user, scope.project, "scan.png", PNG, ["eng"])
    no_text = Recorder(lambda d: ocr_result(d, status="no_text"))
    assert await StudentWorker(jobs, no_text, "w").process_one()
    successor = await jobs.retry(scope.user, scope.project, job.id)
    executor = Recorder()
    assert await StudentWorker(jobs, executor, "w").process_one()
    assert executor.calls == [("png", ("eng",))]
    assert (await jobs.get(scope.user, scope.project, successor.id)).state == "completed"


async def test_legacy_sources_without_a_stored_choice_never_request_ocr(db):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    job = await jobs.submit_raw(scope.user, scope.project, "old.pdf", SCAN)
    async with db.sessionmaker() as session, session.begin():
        revision = await session.get(DocumentRevision, job.input_revision_id)
        revision.meta = {"raw_format": "pdf"}  # as stored before this change
    lease = await jobs.claim("w")
    assert await jobs.raw_input(lease) == (SCAN, "pdf", ())
