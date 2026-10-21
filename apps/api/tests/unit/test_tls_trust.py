"""Actual bundled trust anchors, plus a runtime-image system-store smoke test."""

import ssl

import certifi


def _assert_secure_trust(context: ssl.SSLContext) -> None:
    common_names = {
        value
        for certificate in context.get_ca_certs()
        for relative_name in certificate["subject"]
        for key, value in relative_name
        if key == "commonName"
    }
    # PYSEC-2026-4320 / GHSA-6q48-6c7w-9gw2: compromised intermediates
    # chaining to G3 must not remain trusted. Unaffected emSign roots stay usable.
    assert "emSign ECC Root CA - G3" not in common_names
    assert {
        "ISRG Root X1",
        "emSign Root CA - G1",
        "emSign Root CA - C1",
        "emSign ECC Root CA - C3",
    } <= common_names
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_bundled_trust_excludes_compromised_emsign_root_and_keeps_healthy_roots() -> None:
    _assert_secure_trust(ssl.create_default_context(cafile=certifi.where()))


if __name__ == "__main__":
    test_bundled_trust_excludes_compromised_emsign_root_and_keeps_healthy_roots()
    # Run only inside the rebuilt API image, not against the cloud host's trust.
    _assert_secure_trust(ssl.create_default_context())
    print("Bundled and system TLS trust: compromised root absent; healthy roots retained")
