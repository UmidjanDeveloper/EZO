import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from ezo_api.jarvis.device_protocol import DeviceWork, sign_work, verify_work


def test_server_work_signature_is_pinned_device_bound_expiring_and_tamper_evident():
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    device = uuid.uuid4()
    item = DeviceWork(
        request_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        device_id=device,
        action="files.latest_documents",
        root="downloads",
        count=1,
        extensions=["pdf"],
        expires_at=1100,
    )
    signed = sign_work(item, private)
    verify_work(signed, public, device_id=device, now=1000)
    for wrong_device, now in [(uuid.uuid4(), 1000), (device, 1100), (device, 799)]:
        with pytest.raises(ValueError):
            verify_work(signed, public, device_id=wrong_device, now=now)
    signed.payload.extensions.append("txt")
    with pytest.raises(ValueError):
        verify_work(signed, public, device_id=device, now=1000)
