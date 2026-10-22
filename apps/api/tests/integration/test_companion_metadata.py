"""Actual Linux files, subprocess and persistent replay journal; no OS mocks.

These tests do not establish Windows/Android/iOS support or remote pairing.
"""

import json
import os
import sqlite3
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


def test_nanosecond_metadata_survives_javascript_json_without_number_rounding(device):
    root, journal, _, _, _, options = device
    path = root / "O‘zbekiston-🙂.txt"
    path.write_text("private")
    stamp = 1750000000000000001  # outside IEEE754's exact integer range
    os.utime(path, ns=(stamp, stamp))
    engine = MetadataCompanion(root, journal, **options)
    try:
        result = engine.execute(request(device))
        wire = json.loads(result.model_dump_json())["payload"]["files"][0]
        assert wire["modified_ns"] == str(stamp)
        assert wire["size_bytes"] == "7"
    finally:
        engine.close()


def test_accepted_small_controller_clock_skew_has_verifiable_response(device):
    root, journal, _, key, _, options = device
    now = int(time.time())
    command = request(device, issued_at=now + 3, expires_at=now + 60)
    engine = MetadataCompanion(root, journal, **options)
    try:
        result = engine.execute(command)
        verify_response(result, command.payload, key.public_key(), now=int(time.time()))
    finally:
        engine.close()


def test_existing_unrelated_sqlite_database_is_not_modified_as_a_journal(device):
    root, journal, _, _, _, options = device
    with sqlite3.connect(journal) as connection:
        connection.execute("CREATE TABLE owner_data(value TEXT)")
        connection.execute("INSERT INTO owner_data VALUES ('keep')")
    journal.chmod(0o600)
    with pytest.raises(CompanionError, match="foreign_or_incompatible_journal"):
        companion = MetadataCompanion(root, journal, **options)
        companion.close()
    with sqlite3.connect(journal) as connection:
        assert connection.execute("SELECT value FROM owner_data").fetchone()[0] == "keep"
        assert (
            connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[
                0
            ]
            == 1
        )


def test_local_revocation_is_permanent_across_restart_and_new_request_ids(device):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    engine.revoke()
    engine.revoke()
    engine.close()
    restarted = MetadataCompanion(root, journal, **options)
    try:
        with pytest.raises(CompanionError, match="authority_revoked"):
            restarted.execute(request(device))
        assert (
            restarted._journal.execute("SELECT count(*) FROM metadata_requests").fetchone()[0] == 0
        )
    finally:
        restarted.close()


def test_cancel_before_admission_survives_restart_without_fake_completion(device):
    root, journal, _, _, _, options = device
    command = request(device)
    engine = MetadataCompanion(root, journal, **options)
    assert engine.cancel_request(command.payload.request_id) == "cancelled"
    assert engine.cancel_request(command.payload.request_id) == "cancelled"
    engine.close()
    restarted = MetadataCompanion(root, journal, **options)
    try:
        with pytest.raises(CompanionError, match="cancelled"):
            restarted.execute(command)
        assert (
            restarted._journal.execute("SELECT count(*) FROM metadata_requests").fetchone()[0] == 0
        )
    finally:
        restarted.close()


@pytest.mark.parametrize("operation", ["cancel", "revoke"])
@pytest.mark.parametrize("boundary", ["before_scan", "before_publication"])
def test_other_connection_control_fences_actual_inflight_completion(device, operation, boundary):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    operator = MetadataCompanion(root, journal, **options)
    command = request(device)
    calls = 0

    def control_at_boundary():
        nonlocal calls
        calls += 1
        if calls == (1 if boundary == "before_scan" else 2):
            if operation == "cancel":
                operator.cancel_request(command.payload.request_id)
            else:
                operator.revoke()
        return False

    try:
        with pytest.raises(CompanionError, match=r"cancelled|authority_revoked"):
            engine.execute(command, cancelled=control_at_boundary)
        status, receipt = engine._journal.execute(
            "SELECT status,receipt_sha256 FROM metadata_requests WHERE id=?",
            (str(command.payload.request_id),),
        ).fetchone()
        assert status == ("cancelled" if operation == "cancel" else "revoked")
        assert receipt is None
    finally:
        engine.close()
        operator.close()


def test_late_controls_preserve_historical_receipt_and_do_not_revive_work(device):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    command = request(device)
    try:
        engine.execute(command)
        before = engine._journal.execute("SELECT * FROM metadata_requests").fetchall()
        assert engine.cancel_request(command.payload.request_id) == "already_terminal"
        engine.revoke()
        assert engine._journal.execute("SELECT * FROM metadata_requests").fetchall() == before
        with pytest.raises(CompanionError, match="authority_revoked"):
            engine.execute(command)
    finally:
        engine.close()


def test_v1_upgrade_preserves_replay_and_disallows_old_journal_version_contract(device):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    command = request(device)
    engine.execute(command)
    rows = engine._journal.execute("SELECT * FROM metadata_requests").fetchall()
    engine.close()
    with sqlite3.connect(journal) as db:
        db.execute("DROP TABLE metadata_controls")
        db.execute("DROP TABLE metadata_cancellations")
        db.execute("PRAGMA user_version=1")
    upgraded = MetadataCompanion(root, journal, **options)
    try:
        assert upgraded._journal.execute("SELECT * FROM metadata_requests").fetchall() == rows
        with pytest.raises(CompanionError, match="replayed_request"):
            upgraded.execute(command)
        upgraded.revoke()
        assert int.from_bytes(journal.read_bytes()[60:64], "big") == 2
    finally:
        upgraded.close()


@pytest.mark.parametrize("table", ["metadata_controls", "metadata_requests", "metadata_binding"])
def test_missing_journal_authority_or_replay_state_is_not_silently_reset(device, table):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    engine.revoke()
    engine.close()
    with sqlite3.connect(journal) as db:
        db.execute(f"DROP TABLE {table}")  # fixed test identifiers
    with pytest.raises(CompanionError, match="incomplete_journal"):
        MetadataCompanion(root, journal, **options)


@pytest.mark.parametrize("operation", ["cancel", "revoke"])
def test_real_operator_process_prevents_result_publication(device, operation):
    root, journal, controller, key, identities, options = device
    engine = MetadataCompanion(root, journal, **options)
    command = request(device)
    key_path = journal.parent / "ephemeral-control-test-key"
    key_path.write_bytes(key.private_bytes_raw())
    key_path.chmod(0o600)
    called = False

    def operator_process():
        nonlocal called
        if called:
            return False
        called = True
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
            args += (
                ["--revoke"]
                if operation == "revoke"
                else ["--cancel-request", str(command.payload.request_id)]
            )
            result = subprocess.run(  # noqa: S603 - fixed module; trusted test fixture flags
                args,
                input="",
                capture_output=True,
                text=True,
                pass_fds=(key_file.fileno(),),
                timeout=5,
                check=False,
            )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["outcome"] == (
            "authority_revoked" if operation == "revoke" else "cancelled"
        )
        assert key.private_bytes_raw().hex() not in result.stdout
        return False

    try:
        with pytest.raises(CompanionError, match=r"cancelled|authority_revoked"):
            engine.execute(command, cancelled=operator_process)
        assert (
            engine._journal.execute("SELECT receipt_sha256 FROM metadata_requests").fetchone()[0]
            is None
        )
    finally:
        engine.close()


def test_process_crash_after_admission_does_not_reexecute_or_invent_receipt(device):
    import multiprocessing

    root, journal, _, _, _, options = device
    command = request(device)

    def crash_after_admission():
        engine = MetadataCompanion(root, journal, **options)
        engine.execute(command, cancelled=lambda: os._exit(23))

    process = multiprocessing.get_context("fork").Process(target=crash_after_admission)
    process.start()
    try:
        process.join(timeout=5)
        assert process.exitcode == 23
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    restarted = MetadataCompanion(root, journal, **options)
    try:
        with pytest.raises(CompanionError, match="replayed_request"):
            restarted.execute(command)
        assert restarted._journal.execute(
            "SELECT status,receipt_sha256 FROM metadata_requests"
        ).fetchone() == ("started", None)
    finally:
        restarted.close()


def test_cancellation_budget_never_resets_but_duplicate_cancel_remains_idempotent(device):
    root, journal, _, _, _, options = device
    engine = MetadataCompanion(root, journal, **options)
    ids = [str(uuid.uuid4()) for _ in range(10000)]
    try:
        engine._journal.execute("BEGIN")
        engine._journal.executemany(
            "INSERT INTO metadata_cancellations VALUES (?,1)", ((item,) for item in ids)
        )
        engine._journal.execute("COMMIT")
        assert engine.cancel_request(uuid.UUID(ids[0])) == "cancelled"
        with pytest.raises(CompanionError, match="cancellation_budget_exhausted"):
            engine.cancel_request(uuid.uuid4())
        assert (
            engine._journal.execute("SELECT count(*) FROM metadata_cancellations").fetchone()[0]
            == 10000
        )
    finally:
        engine.close()
