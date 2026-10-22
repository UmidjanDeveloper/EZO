"""Fixed read-only Linux companion operation; no shell or document parser.

Run by the owner as a separate unprivileged process. Directory, trust keys and
identity are operator configuration, never fields supplied by a model/request.
Windows is refused until its handle/DACL boundary is implemented and tested.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ezo_api.companion.protocol import (
    CompanionError,
    FileMetadata,
    MetadataResponse,
    SignedRequest,
    SignedResponse,
    canonical,
    request_hash,
    sign_response,
    verify_request,
)

MAX_ENTRIES = 1000
MAX_REQUESTS = 10000
JOURNAL_APPLICATION_ID = 0x455A4F31  # EZO1; never open an arbitrary owner database


class MetadataCompanion:
    def __init__(
        self,
        root: Path,
        journal: Path,
        *,
        actor_id: uuid.UUID,
        device_id: uuid.UUID,
        root_id: uuid.UUID,
        controller_key: Ed25519PublicKey,
        device_key: Ed25519PrivateKey,
    ) -> None:
        if (
            not sys.platform.startswith("linux")
            or not hasattr(os, "O_NOFOLLOW")
            or os.scandir not in os.supports_fd
            or os.geteuid() != os.getuid()
            or os.geteuid() == 0
        ):
            raise CompanionError("unsupported_or_privileged_host")
        self.actor_id, self.device_id, self.root_id = actor_id, device_id, root_id
        self.controller_key, self.device_key = controller_key, device_key
        self._fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            root_stat = os.fstat(self._fd)
            if root_stat.st_uid != os.geteuid():
                raise CompanionError("root_owner_mismatch")
            identity = f"{root_id}:{root_stat.st_dev}:{root_stat.st_ino}"
            self._root_identity = hashlib.sha256(identity.encode()).hexdigest()
            self._journal = self._open_journal(journal)
            self._bind_journal()
        except BaseException:
            if hasattr(self, "_journal"):
                self._journal.close()
            os.close(self._fd)
            self._fd = -1
            raise

    def _bind_journal(self) -> None:
        identity = ":".join(
            [
                str(self.actor_id),
                str(self.device_id),
                str(self.root_id),
                self._root_identity,
                self.controller_key.public_bytes_raw().hex(),
                self.device_key.public_key().public_bytes_raw().hex(),
            ]
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        try:
            self._journal.execute("BEGIN IMMEDIATE")
            self._journal.execute(
                "CREATE TABLE IF NOT EXISTS metadata_binding (id INTEGER PRIMARY KEY CHECK(id=1), "
                "identity_sha256 TEXT NOT NULL)"
            )
            row = self._journal.execute(
                "SELECT identity_sha256 FROM metadata_binding WHERE id=1"
            ).fetchone()
            if row is None:
                self._journal.execute("INSERT INTO metadata_binding VALUES (1,?)", (digest,))
            elif row[0] != digest:
                raise CompanionError("journal_identity_mismatch")
            self._journal.execute("COMMIT")
        except BaseException:
            if self._journal.in_transaction:
                self._journal.execute("ROLLBACK")
            raise

    @staticmethod
    def _open_journal(path: Path) -> sqlite3.Connection:
        parent = path.parent.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o077
        ):
            raise CompanionError("journal_requires_private_owned_directory")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
            ):
                raise CompanionError("unsafe_journal")
            if info.st_size:
                header = os.pread(fd, 100, 0)
                if (
                    len(header) != 100
                    or header[:16] != b"SQLite format 3\x00"
                    or int.from_bytes(header[68:72], "big") != JOURNAL_APPLICATION_ID
                    or int.from_bytes(header[60:64], "big") != 1
                ):
                    raise CompanionError("foreign_or_incompatible_journal")
        finally:
            os.close(fd)
        connection = sqlite3.connect(path, timeout=1, isolation_level=None)
        try:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN IMMEDIATE")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application_id == 0 and not info.st_size:
                tables = connection.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
                if tables:
                    raise CompanionError("foreign_or_incompatible_journal")
                connection.execute("PRAGMA application_id=0x455A4F31")
                connection.execute("PRAGMA user_version=1")
            elif application_id != JOURNAL_APPLICATION_ID or version != 1:
                raise CompanionError("foreign_or_incompatible_journal")
            connection.execute("PRAGMA max_page_count=4096")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata_requests ("
                "id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, "
                "started_at INTEGER NOT NULL, status TEXT NOT NULL, receipt_sha256 TEXT)"
            )
            connection.execute("COMMIT")
            return connection
        except BaseException:
            connection.close()
            raise

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
        self._journal.close()

    def _admit(self, request: SignedRequest, now: int) -> None:
        payload = request.payload
        verify_request(request, self.controller_key)
        if (
            payload.actor_id != self.actor_id
            or payload.device_id != self.device_id
            or payload.root_id != self.root_id
        ):
            raise CompanionError("request_scope_mismatch")
        if payload.issued_at > now + 5 or now >= payload.expires_at:
            raise CompanionError("request_expired_or_future")
        try:
            self._journal.execute("BEGIN IMMEDIATE")
            if (
                self._journal.execute("SELECT count(*) FROM metadata_requests").fetchone()[0]
                >= MAX_REQUESTS
            ):
                raise CompanionError("device_request_budget_exhausted")
            self._journal.execute(
                "INSERT INTO metadata_requests(id,request_sha256,started_at,status) "
                "VALUES (?,?,?,?)",
                (str(payload.request_id), request_hash(payload), now, "started"),
            )
            self._journal.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self._journal.execute("ROLLBACK")
            raise CompanionError("replayed_request") from exc
        except BaseException:
            if self._journal.in_transaction:
                self._journal.execute("ROLLBACK")
            raise

    def execute(
        self, request: SignedRequest, *, cancelled: Callable[[], bool] = lambda: False
    ) -> SignedResponse:
        if self._fd < 0:
            raise CompanionError("companion_closed")
        now = int(time.time())
        self._admit(request, now)
        payload = request.payload
        try:
            if cancelled():
                raise CompanionError("cancelled")
            files: list[FileMetadata] = []
            examined = 0
            complete = True
            started = time.monotonic()
            with os.scandir(self._fd) as entries:
                for entry in entries:
                    if cancelled():
                        raise CompanionError("cancelled")
                    if time.monotonic() - started > 2 or int(time.time()) >= payload.expires_at:
                        raise CompanionError("deadline_exceeded")
                    if examined >= MAX_ENTRIES:
                        complete = False
                        break
                    examined += 1
                    try:
                        entry.name.encode("utf-8")
                        info = entry.stat(follow_symlinks=False)
                    except (OSError, UnicodeError):
                        complete = False
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        continue  # no links, directories, FIFOs, sockets or device files
                    identity = (
                        f"{self.device_id}:{self.root_id}:{entry.name}:"
                        f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}"
                    )
                    files.append(
                        FileMetadata(
                            file_id=hashlib.sha256(identity.encode()).hexdigest(),
                            name=entry.name,
                            size_bytes=str(info.st_size),
                            modified_ns=str(info.st_mtime_ns),
                        )
                    )
            files.sort(key=lambda item: (-int(item.modified_ns), item.name))
            if cancelled():
                raise CompanionError("cancelled")
            if int(time.time()) >= payload.expires_at:
                raise CompanionError("deadline_exceeded")
            response = MetadataResponse(
                request_id=payload.request_id,
                request_sha256=request_hash(payload),
                actor_id=self.actor_id,
                device_id=self.device_id,
                task_id=payload.task_id,
                root_id=self.root_id,
                root_identity_sha256=self._root_identity,
                files=files[: payload.limit],
                complete_scan=complete,
                latest_ambiguous=not complete
                or (len(files) > 1 and files[0].modified_ns == files[1].modified_ns),
                examined_entries=examined,
                created_at=int(time.time()),
            )
            signed = sign_response(response, self.device_key)
            self._journal.execute(
                "UPDATE metadata_requests SET status=?,receipt_sha256=? WHERE id=?",
                (
                    "completed_metadata_scan",
                    hashlib.sha256(canonical(response)).hexdigest(),
                    str(payload.request_id),
                ),
            )
            return signed
        except BaseException:
            self._journal.execute(
                "UPDATE metadata_requests SET status=? WHERE id=?",
                ("interrupted", str(payload.request_id)),
            )
            raise


def main() -> None:
    """One signed request over stdin. Private key is read from an inherited FD.

    No listener, automatic discovery, generated key, package installer, shell or
    model is started. This CLI is not called or imported by the API process.
    """
    import argparse
    import json

    from pydantic import ValidationError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--actor-id", type=uuid.UUID, required=True)
    parser.add_argument("--device-id", type=uuid.UUID, required=True)
    parser.add_argument("--root-id", type=uuid.UUID, required=True)
    parser.add_argument("--controller-public-key", required=True)
    parser.add_argument("--device-key-fd", type=int, required=True)
    args = parser.parse_args()
    companion = None
    try:
        if args.device_key_fd < 3:
            raise CompanionError("private_key_requires_inherited_fd")
        key_bytes = os.read(args.device_key_fd, 33)
        device_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
        controller_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(args.controller_public_key)
        )
        data = sys.stdin.buffer.read(8193)
        if len(data) > 8192:
            raise CompanionError("request_size_limit")
        request = SignedRequest.model_validate_json(data)
        companion = MetadataCompanion(
            args.root,
            args.journal,
            actor_id=args.actor_id,
            device_id=args.device_id,
            root_id=args.root_id,
            controller_key=controller_key,
            device_key=device_key,
        )
        result = companion.execute(request)
        print(result.model_dump_json())
    except (CompanionError, OSError, ValueError, sqlite3.Error, ValidationError) as exc:
        code = exc.code if isinstance(exc, CompanionError) else "configuration_or_request_rejected"
        print(json.dumps({"error": {"code": code}, "outcome": "not_completed"}))
        raise SystemExit(2) from None
    finally:
        if companion is not None:
            companion.close()


if __name__ == "__main__":
    main()
