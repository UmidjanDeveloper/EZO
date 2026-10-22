"""Actual Linux files, subprocess and persistent replay journal; no OS mocks.

These tests do not establish Windows/Android/iOS support or remote pairing.
"""

import json
import os
import subprocess
import sys
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from ezo_api.companion.metadata import MetadataCompanion
from ezo_api.companion.protocol import (
    CompanionError,
    MetadataRequest,
    SignedResponse,
    sign_request,
    sign_response,
    verify_response,
)

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.geteuid() == 0,
    reason="Real unprivileged Linux companion boundary; Windows is unsupported",
)


@pytest.fixture
def device(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir(mode=0o700)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    controller = Ed25519PrivateKey.generate()  # ephemeral test keys, never production
    key = Ed25519PrivateKey.generate()
    identities = {name: uuid.uuid4() for name in ("actor_id", "device_id", "root_id")}
    options = {**identities, "controller_key": controller.public_key(), "device_key": key}
    return root, private / "journal.sqlite", controller, key, identities, options


def request(device, **changes):
    _, _, controller, _, identities, _ = device
    now = int(time.time())
    payload = MetadataRequest(
        **{
            **identities,
            "request_id": uuid.uuid4(),
            "task_id": uuid.uuid4(),
            "action": "file.metadata.list",
            "issued_at": now,
            "expires_at": now + 60,
            **changes,
        }
    )
    return sign_request(payload, controller)


def test_real_metadata_never_reads_bodies_links_or_special_files(device):
    root, journal, _, key, _, options = device
    (root / "older.txt").write_text("DO_NOT_EXFILTRATE_BODY")
    (root / "latest.pdf").write_bytes(b"arbitrary bytes, not parsed")
    os.utime(root / "older.txt", ns=(1, 1))
    (root / "directory").mkdir()
    (root / "outside-link").symlink_to(journal.parent)
    os.mkfifo(root / "never-open-this-fifo")
    engine = MetadataCompanion(root, journal, **options)
    try:
        command = request(device)
        result = engine.execute(command)
        verify_response(result, command.payload, key.public_key(), now=int(time.time()))
        assert [f.name for f in result.payload.files] == ["latest.pdf", "older.txt"]
        assert "DO_NOT_EXFILTRATE_BODY" not in result.model_dump_json()
        assert result.payload.complete_scan is True
        assert result.payload.latest_ambiguous is False
        assert str(root) not in result.model_dump_json()
    finally:
        engine.close()


def test_replay_fencing_survives_actual_restart_and_root_rename(device):
    root, journal, _, _, _, options = device
    (root / "original.txt").write_text("original")
    engine = MetadataCompanion(root, journal, **options)
    command = request(device)
    try:
        root.rename(root.with_name("original-root"))
        root.mkdir(mode=0o700)
        (root / "replacement.txt").write_text("not consented")
        assert [f.name for f in engine.execute(command).payload.files] == ["original.txt"]
    finally:
        engine.close()
    restarted = MetadataCompanion(root.with_name("original-root"), journal, **options)
    try:
        with pytest.raises(CompanionError, match="replayed_request"):
            restarted.execute(command)
    finally:
        restarted.close()


def test_restart_cannot_rebind_consent_to_replacement_directory(device):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    engine.close()
    root.rename(root.with_name("original-root"))
    root.mkdir(mode=0o700)
    with pytest.raises(CompanionError, match="journal_identity_mismatch"):
        replacement = MetadataCompanion(root, journal, **options)
        replacement.close()


@pytest.mark.parametrize("field", ["actor_id", "device_id", "root_id"])
def test_signed_wrong_scope_does_not_authorize_any_read(device, field):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    try:
        with pytest.raises(CompanionError, match="scope_mismatch"):
            engine.execute(request(device, **{field: uuid.uuid4()}))
        assert engine._journal.execute("SELECT count(*) FROM metadata_requests").fetchone()[0] == 0
    finally:
        engine.close()


def test_forgery_deadlines_cancellation_and_response_task_confusion(device):
    root, journal, _, key, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    try:
        valid = request(device)
        forged = sign_request(valid.payload, Ed25519PrivateKey.generate())
        with pytest.raises(CompanionError, match="invalid_signature"):
            engine.execute(forged)
        now = int(time.time())
        with pytest.raises(CompanionError, match="expired_or_future"):
            engine.execute(request(device, issued_at=now - 120, expires_at=now - 60))
        cancelled = request(device)
        with pytest.raises(CompanionError, match="cancelled"):
            engine.execute(cancelled, cancelled=lambda: True)
        with pytest.raises(CompanionError, match="replayed_request"):
            engine.execute(cancelled)
        result = engine.execute(valid)
        wrong_task = sign_response(result.payload.model_copy(update={"task_id": uuid.uuid4()}), key)
        with pytest.raises(CompanionError, match="scope_or_deadline"):
            verify_response(wrong_task, valid.payload, key.public_key(), now=int(time.time()))
    finally:
        engine.close()


def test_request_cannot_supply_shell_path_or_infinite_lifetime(device):
    payload = request(device).payload.model_dump(mode="json")
    for change in (
        {"path": "/etc"},
        {"shell": "whoami"},
        {"action": "telegram.send"},
        {"expires_at": payload["issued_at"] + 3600},
        {"limit": 100000},
    ):
        with pytest.raises(ValidationError):
            MetadataRequest.model_validate({**payload, **change})


def test_real_companion_subprocess_and_private_key_fd(device):
    root, journal, controller, key, identities, _ = device
    (root / "hisobot.txt").write_text("PRIVATE_FILE_BODY")
    key_path = journal.parent / "ephemeral-test-key"
    key_path.write_bytes(key.private_bytes_raw())
    key_path.chmod(0o600)
    command = request(device)
    with key_path.open("rb") as key_file:
        args = [
            sys.executable,
            "-m",
            "ezo_api.companion.metadata",
            "--root",
            str(root),
            "--journal",
            str(journal),
            "--controller-public-key",
            controller.public_key().public_bytes_raw().hex(),
            "--device-key-fd",
            str(key_file.fileno()),
        ]
        for name, value in identities.items():
            args += ["--" + name.replace("_", "-"), str(value)]
        result = subprocess.run(  # noqa: S603 - fixed test interpreter/module; request is stdin data
            args,
            input=command.model_dump_json(),
            capture_output=True,
            text=True,
            pass_fds=(key_file.fileno(),),
            timeout=5,
            check=False,
        )
    assert result.returncode == 0, result.stderr
    signed = SignedResponse.model_validate_json(result.stdout)
    verify_response(signed, command.payload, key.public_key(), now=int(time.time()))
    assert signed.payload.files[0].name == "hisobot.txt"
    assert (
        "PRIVATE_FILE_BODY" not in result.stdout
        and key.private_bytes_raw().hex() not in result.stdout
    )
    assert json.loads(result.stdout)["payload"]["outcome"] == "completed_metadata_scan"


def test_real_scan_budget_marks_partial_ordering_not_latest_download(device):
    root, journal, _, _, _, options = device
    for index in range(1001):
        (root / f"file-{index}").touch()
    engine = MetadataCompanion(root, journal, **options)
    try:
        result = engine.execute(request(device, limit=1)).payload
        assert result.examined_entries == 1000
        assert len(result.files) == 1
        assert result.complete_scan is False and result.latest_ambiguous is True
    finally:
        engine.close()


def test_request_budget_is_consumed_and_never_automatically_reset(device):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    try:
        engine._journal.execute("BEGIN")
        engine._journal.executemany(
            "INSERT INTO metadata_requests VALUES (?,?,?,?,?)",
            ((str(uuid.uuid4()), "a" * 64, 1, "interrupted", None) for _ in range(10000)),
        )
        engine._journal.execute("COMMIT")
        with pytest.raises(CompanionError, match="budget_exhausted"):
            engine.execute(request(device))
        assert (
            engine._journal.execute("SELECT count(*) FROM metadata_requests").fetchone()[0] == 10000
        )
    finally:
        engine.close()


def test_public_journal_and_symlink_journal_are_rejected(device):
    root, journal, _, _, _, options = device
    journal.touch(mode=0o644)
    journal.chmod(0o644)
    with pytest.raises(CompanionError, match="unsafe_journal"):
        MetadataCompanion(root, journal, **options)
    journal.unlink()
    outside = journal.parent / "outside"
    outside.touch(mode=0o600)
    journal.symlink_to(outside)
    with pytest.raises(OSError):
        MetadataCompanion(root, journal, **options)
