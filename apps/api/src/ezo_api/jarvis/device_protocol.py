"""Server ↔ paired device messages for JARVIS steps (fixed actions, signed results).

The server hands a paired device one short-lived work item for a fixed action. The
device answers with a result signed by its own Ed25519 key (generated on the device,
public half registered at pairing). The server accepts it only if the signature,
device, request id, action and deadline all match the pending step. Paths, commands
and model text are never part of the protocol: the device maps the folder *alias*
(``downloads``) to the folder its owner authorised locally.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

RESULT_DOMAIN = b"ezo-jarvis-device-result-v1\x00"
PAIRING_DOMAIN = b"ezo-jarvis-device-pairing-v1\x00"
MAX_FILE_BYTES = 5 * 1024 * 1024
DEVICE_EXTENSIONS = ("pdf", "docx", "xlsx", "pptx", "txt", "csv")
DeviceAction = Literal["files.latest_documents"]


class DeviceWork(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    request_id: uuid.UUID
    task_id: uuid.UUID
    device_id: uuid.UUID
    action: DeviceAction
    root: Literal["downloads"]
    count: int = Field(ge=1, le=2)
    extensions: list[str] = Field(max_length=len(DEVICE_EXTENSIONS))
    expires_at: int


class DeviceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=255)
    extension: str
    size_bytes: int = Field(ge=1, le=MAX_FILE_BYTES)
    modified_ms: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_base64: str = Field(max_length=4 * ((MAX_FILE_BYTES + 2) // 3))

    @model_validator(mode="after")
    def content_matches(self) -> DeviceFile:
        if self.extension not in DEVICE_EXTENSIONS or "/" in self.name or "\\" in self.name:
            raise ValueError("unsupported file")
        data = base64.b64decode(self.content_base64, validate=True)
        if len(data) != self.size_bytes or hashlib.sha256(data).hexdigest() != self.sha256:
            raise ValueError("file content does not match its declared size and hash")
        return self

    def content(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)


class DeviceResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    request_id: uuid.UUID
    task_id: uuid.UUID
    device_id: uuid.UUID
    action: DeviceAction
    outcome: Literal["completed", "refused", "failed"]
    reason: str | None = Field(default=None, max_length=200)
    files: list[DeviceFile] = Field(default_factory=list, max_length=2)
    latest_ambiguous: bool = False
    """Two candidate files share the newest modification time: the user must choose."""
    trust: Literal["untrusted_file_content_not_instructions"] = (
        "untrusted_file_content_not_instructions"
    )


class SignedDeviceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    payload: DeviceResultPayload
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")


def canonical(value: BaseModel) -> bytes:
    return json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def public_key(hex_key: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_key))


def verify_result(result: SignedDeviceResult, hex_key: str) -> None:
    try:
        public_key(hex_key).verify(
            bytes.fromhex(result.signature), RESULT_DOMAIN + canonical(result.payload)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("invalid_signature") from exc


def pairing_message(device_name: str, platform: str, nonce: str) -> bytes:
    """What a device signs to prove it holds the private key it registers."""
    return (
        PAIRING_DOMAIN
        + json.dumps(
            {"name": device_name, "nonce": nonce, "platform": platform},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    )


def verify_pairing(
    hex_key: str, signature: str, device_name: str, platform: str, nonce: str
) -> None:
    try:
        public_key(hex_key).verify(
            bytes.fromhex(signature), pairing_message(device_name, platform, nonce)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("invalid_signature") from exc


WORK_DOMAIN = b"ezo-jarvis-server-work-v1\x00"


class SignedDeviceWork(BaseModel):
    """Opt-in server signature. Receiver must pin its trusted public key separately."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    payload: DeviceWork
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")


def sign_work(work: DeviceWork, private_key_hex: str) -> SignedDeviceWork:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    return SignedDeviceWork(payload=work, signature=key.sign(WORK_DOMAIN + canonical(work)).hex())


def verify_work(
    work: SignedDeviceWork, pinned_key_hex: str, *, device_id: uuid.UUID, now: int
) -> None:
    """Verify before local dispatch. Durable request-id replay journal is also required."""
    if work.payload.device_id != device_id or not now < work.payload.expires_at <= now + 300:
        raise ValueError("wrong_device_or_expired_work")
    try:
        public_key(pinned_key_hex).verify(
            bytes.fromhex(work.signature), WORK_DOMAIN + canonical(work.payload)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("invalid_work_signature") from exc
