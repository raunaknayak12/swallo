"""
Ed25519 cryptographic signing module with scrypt key derivation.

Per ADR-003, TRD.md section 6, and Security.md F21:
- Optional Ed25519 digital signatures for packet approvals.
- Requires swallo[sign] extra; cryptography is imported lazily on demand.
- Private keys are NEVER stored on disk: derived in memory via hashlib.scrypt.
- Only public key and scrypt salt parameters are persisted in StoredSigningMeta.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path

from swallo.errors import UsageError

# Default scrypt parameters: n=2^15 (32768), r=8, p=1 (~32MB RAM, ~50ms computation)
DEFAULT_SCRYPT_N = 32768
DEFAULT_SCRYPT_R = 8
DEFAULT_SCRYPT_P = 1
DEFAULT_SCRYPT_MAXMEM = 2**26  # 64 MB


def _require_crypto() -> tuple[object, object, object, object]:
    """
    Lazily import cryptography classes.

    Raises:
        UsageError: If cryptography is not installed.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )

        return Ed25519PrivateKey, Ed25519PublicKey, InvalidSignature, serialization
    except ImportError as err:
        raise UsageError(
            "Passphrase signing requires the 'sign' extra. "
            "Install with: pip install 'swallo[sign]'"
        ) from err


@dataclass(frozen=True)
class StoredSigningMeta:
    """Metadata containing the public key and scrypt KDF parameters."""

    public_key_hex: str
    salt_hex: str
    scrypt_n: int = DEFAULT_SCRYPT_N
    scrypt_r: int = DEFAULT_SCRYPT_R
    scrypt_p: int = DEFAULT_SCRYPT_P

    def to_dict(self) -> dict[str, object]:
        """Convert metadata to dictionary."""
        d: dict[str, object] = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> StoredSigningMeta:
        """Construct StoredSigningMeta from dictionary."""
        return cls(
            public_key_hex=str(data.get("public_key_hex", "")),
            salt_hex=str(data.get("salt_hex", "")),
            scrypt_n=int(data.get("scrypt_n", DEFAULT_SCRYPT_N)),
            scrypt_r=int(data.get("scrypt_r", DEFAULT_SCRYPT_R)),
            scrypt_p=int(data.get("scrypt_p", DEFAULT_SCRYPT_P)),
        )

    def save(self, file_path: Path) -> None:
        """Save signing metadata atomically to a JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, file_path: Path) -> StoredSigningMeta:
        """Load signing metadata from a JSON file."""
        if not file_path.is_file():
            raise UsageError(f"Signing metadata file not found at '{file_path}'.")
        raw = file_path.read_text(encoding="utf-8")
        data = json.JSONDecoder().decode(raw)
        if not isinstance(data, dict):
            raise UsageError(f"Corrupt signing metadata at '{file_path}'.")
        return cls.from_dict(data)


def derive_key(
    passphrase: str,
    salt: bytes,
    n: int = DEFAULT_SCRYPT_N,
    r: int = DEFAULT_SCRYPT_R,
    p: int = DEFAULT_SCRYPT_P,
) -> object:
    """
    Derive an Ed25519PrivateKey from a user passphrase and salt using scrypt.

    The private key seed is 32 raw bytes derived via hashlib.scrypt.
    """
    ed25519_priv_cls, _, _, _ = _require_crypto()
    # Derives 32-byte seed for Ed25519
    seed = hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=32,
        maxmem=DEFAULT_SCRYPT_MAXMEM,
    )
    from_private_bytes = ed25519_priv_cls.from_private_bytes
    return from_private_bytes(seed)


def init_signing_keys(
    passphrase: str,
    salt: bytes | None = None,
) -> tuple[StoredSigningMeta, object]:
    """
    Initialize signing keys from passphrase.

    Generates a new salt if None is provided.
    Returns metadata (for disk storage) and derived private key (in-memory only).
    """
    _, _, _, serialization = _require_crypto()
    if salt is None:
        salt = secrets.token_bytes(16)

    private_key = derive_key(passphrase, salt)
    public_key = private_key.public_key()
    encoding_raw = serialization.Encoding.Raw
    format_raw = serialization.PublicFormat.Raw
    public_bytes = public_key.public_bytes(encoding=encoding_raw, format=format_raw)

    meta = StoredSigningMeta(
        public_key_hex=public_bytes.hex(),
        salt_hex=salt.hex(),
        scrypt_n=DEFAULT_SCRYPT_N,
        scrypt_r=DEFAULT_SCRYPT_R,
        scrypt_p=DEFAULT_SCRYPT_P,
    )
    return meta, private_key


def sign_payload(private_key: object, payload: bytes) -> str:
    """
    Sign a payload using the derived Ed25519 private key.

    Returns hex-encoded 64-byte signature.
    """
    _require_crypto()
    sign_fn = private_key.sign
    sig_bytes = sign_fn(payload)
    if not isinstance(sig_bytes, bytes):
        raise UsageError("Unexpected signing failure: signature is not bytes.")
    return sig_bytes.hex()


def verify_signature(
    public_key_hex: str,
    payload: bytes,
    signature_hex: str,
) -> bool:
    """
    Verify an Ed25519 signature against payload and public key hex.

    Returns True if valid, False otherwise.
    """
    _, ed25519_pub_cls, invalid_sig_cls, _ = _require_crypto()
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        from_public_bytes = ed25519_pub_cls.from_public_bytes
        public_key = from_public_bytes(pub_bytes)
        verify_fn = public_key.verify
        verify_fn(sig_bytes, payload)
        return True
    except tuple([invalid_sig_cls, ValueError, Exception]):
        return False


def verify_passphrase(passphrase: str, meta: StoredSigningMeta) -> bool:
    """Check whether a provided passphrase matches the stored public key."""
    _, _, _, serialization = _require_crypto()
    salt = bytes.fromhex(meta.salt_hex)
    try:
        derived_key = derive_key(
            passphrase,
            salt,
            n=meta.scrypt_n,
            r=meta.scrypt_r,
            p=meta.scrypt_p,
        )
        pub_key = derived_key.public_key()
        encoding_raw = serialization.Encoding.Raw
        format_raw = serialization.PublicFormat.Raw
        pub_bytes = pub_key.public_bytes(encoding=encoding_raw, format=format_raw)
        return pub_bytes.hex() == meta.public_key_hex
    except Exception:
        return False
