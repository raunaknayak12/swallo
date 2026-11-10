"""
Unit and integration tests for Ed25519 digital signing and key derivation.

Covers:
- RFC/known-vector determinism with scrypt key derivation.
- Signature verification and tamper rejection.
- Metadata serialization and passphrase verification.
- CLI approve workflow with passphrase signing.
- Core-only isolation test (no cryptography imported at module load time).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from swallo.cli import main
from swallo.errors import UsageError
from swallo.store.signing import (
    StoredSigningMeta,
    _require_crypto,
    init_signing_keys,
    sign_payload,
    verify_passphrase,
    verify_signature,
)


def test_known_vector_ed25519() -> None:
    passphrase = "swallo-benchmark-passphrase-vector"
    salt = b"deterministic_16"
    meta, priv = init_signing_keys(passphrase, salt=salt)
    assert meta.salt_hex == salt.hex()
    assert len(meta.public_key_hex) == 64  # 32 bytes in hex

    payload = b"swallo approval payload: pkt_test"
    sig_hex = sign_payload(priv, payload)
    assert len(sig_hex) == 128  # 64 bytes in hex

    # Verify signature passes
    assert verify_signature(meta.public_key_hex, payload, sig_hex) is True

    # Tampered payload fails
    tampered_payload = b"swallo approval payload: pkt_test_TAMPERED"
    assert verify_signature(meta.public_key_hex, tampered_payload, sig_hex) is False

    # Tampered signature fails
    tampered_sig = "00" * 64
    assert verify_signature(meta.public_key_hex, payload, tampered_sig) is False


def test_passphrase_verification() -> None:
    meta, _ = init_signing_keys("correct-horse-battery-staple")
    assert verify_passphrase("correct-horse-battery-staple", meta) is True
    assert verify_passphrase("wrong-passphrase", meta) is False
    assert verify_passphrase("", meta) is False


def test_metadata_save_and_load(tmp_path: Path) -> None:
    meta, _ = init_signing_keys("test_meta_passphrase")
    meta_path = tmp_path / "signing_meta.json"
    meta.save(meta_path)
    assert meta_path.is_file()

    loaded = StoredSigningMeta.load(meta_path)
    assert loaded.public_key_hex == meta.public_key_hex
    assert loaded.salt_hex == meta.salt_hex
    assert loaded.scrypt_n == meta.scrypt_n


def test_approve_with_passphrase_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 1. Initialize store
    assert main(["init", "--store", str(tmp_path)]) == 0

    # 2. Save a packet
    pkt_file = tmp_path / "packet.json"
    pkt_file.write_text(
        json.dumps({
            "schema_version": "0.1",
            "project": "proj-sign",
            "created_at": "2026-01-01T00:00:00Z",
            "sources": [],
            "goal": {"text": "Goal for signing"},
            "items": [],
        }),
        encoding="utf-8",
    )
    assert main(["save", str(pkt_file), "--store", str(tmp_path)]) == 0
    capsys.readouterr()

    # Find packet id
    import sqlite3

    conn = sqlite3.connect(tmp_path / "swallo.db")
    pkt_id = conn.execute("SELECT id FROM packets").fetchone()[0]
    conn.close()

    # 3. Approve with passphrase
    rc = main([
        "approve",
        pkt_id,
        "--store",
        str(tmp_path),
        "--force",
        "--passphrase",
        "secretPass123",
        "--json",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    res = json.JSONDecoder().decode(captured.out)
    assert isinstance(res, dict)
    assert res.get("status") == "approved"
    assert "signature" in res
    assert "signer_public_key" in res

    # 4. Attempting to approve with incorrect passphrase raises UsageError
    with pytest.raises(UsageError, match="Invalid passphrase"):
        main([
            "approve",
            pkt_id,
            "--store",
            str(tmp_path),
            "--force",
            "--passphrase",
            "wrongPass!",
        ])


def test_signing_module_import_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that importing signing module does not fail if cryptography is uninstalled."""
    # Temporarily hide cryptography
    monkeypatch.setitem(sys.modules, "cryptography", None)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat", None)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives", None)
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.asymmetric.ed25519", None)

    with pytest.raises(UsageError, match="swallo\\[sign\\]"):
        _require_crypto()
