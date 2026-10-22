"""Signed fixed-operation messages. No filesystem path, shell or model instruction.

OpenJarvis's typed tool/trace interfaces and signed skill manifests inform the
interface; EZO supplies its own scoped protocol and authorization. No upstream
runtime is imported. Cryptographic signatures authenticate messages, not OS safety.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

REQUEST_DOMAIN = b"ezo-companion-metadata-request-v1\x00"
RESPONSE_DOMAIN = b"ezo-companion-metadata-response-v1\x00"


class CompanionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    request_id: uuid.UUID
    actor_id: uuid.UUID
    device_id: uuid.UUID
    task_id: uuid.UUID
    root_id: uuid.UUID
    action: Literal["file.metadata.list"]
    issued_at: int = Field(strict=True, ge=1, le=2**53 - 1)
    expires_at: int = Field(strict=True, ge=1, le=2**53 - 1)
    limit: int = Field(default=20, strict=True, ge=1, le=50)

    @model_validator(mode="after")
    def short_lifetime(self) -> MetadataRequest:
        if not 0 < self.expires_at - self.issued_at <= 60:
            raise ValueError("Companion requests require a lifetime of at most60 seconds.")
        return self


class SignedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    payload: MetadataRequest
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")


def canonical(value: BaseModel) -> bytes:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()


def request_hash(request: MetadataRequest) -> str:
    return hashlib.sha256(REQUEST_DOMAIN + canonical(request)).hexdigest()


def sign_request(request: MetadataRequest, key: Ed25519PrivateKey) -> SignedRequest:
    return SignedRequest(
        payload=request, signature=key.sign(REQUEST_DOMAIN + canonical(request)).hex()
    )


def verify_request(request: SignedRequest, key: Ed25519PublicKey) -> None:
    try:
        key.verify(bytes.fromhex(request.signature), REQUEST_DOMAIN + canonical(request.payload))
    except InvalidSignature as exc:
        raise CompanionError("invalid_signature") from exc


class FileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    file_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(max_length=255)
    size_bytes: int = Field(ge=0)
    modified_ns: int


class MetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    request_id: uuid.UUID
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor_id: uuid.UUID
    device_id: uuid.UUID
    task_id: uuid.UUID
    root_id: uuid.UUID
    root_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: Literal["file.metadata.list"] = "file.metadata.list"
    outcome: Literal["completed_metadata_scan"] = "completed_metadata_scan"
    files: list[FileMetadata] = Field(max_length=50)
    complete_scan: bool
    latest_ambiguous: bool
    examined_entries: int = Field(ge=0, le=1000)
    created_at: int
    trust: Literal["untrusted_file_metadata_not_instructions"] = (
        "untrusted_file_metadata_not_instructions"
    )


class SignedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    payload: MetadataResponse
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")


def sign_response(response: MetadataResponse, key: Ed25519PrivateKey) -> SignedResponse:
    return SignedResponse(
        payload=response, signature=key.sign(RESPONSE_DOMAIN + canonical(response)).hex()
    )


def verify_response(
    response: SignedResponse, request: MetadataRequest, key: Ed25519PublicKey, *, now: int
) -> None:
    try:
        key.verify(bytes.fromhex(response.signature), RESPONSE_DOMAIN + canonical(response.payload))
    except InvalidSignature as exc:
        raise CompanionError("invalid_signature") from exc
    result = response.payload
    if (
        result.request_sha256 != request_hash(request)
        or any(
            getattr(result, name) != getattr(request, name)
            for name in ("request_id", "actor_id", "device_id", "task_id", "root_id")
        )
        or not request.issued_at <= result.created_at < request.expires_at
        or now >= request.expires_at
        or result.created_at > now + 5
    ):
        raise CompanionError("response_scope_or_deadline")
