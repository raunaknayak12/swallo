"""
Content-addressed object store with atomic writes for swallo.

Per ADR-005, TRD.md section 5.2 and IMPLEMENTATION_PLAN.md Step 2:
- Sharded filesystem layout: objects/<first-2-hex>/<rest-of-hash>
- Atomic writes: write to temp file in destination shard, fsync, os.replace.
- Referenced by content hash (sha256:<hex>) only.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
from pathlib import Path

from swallo.errors import IntegrityError


class ObjectStore:
    """Content-addressed filesystem object store for raw/redacted transcripts and artifacts."""

    def __init__(self, store_dir: Path | str) -> None:
        self.base_dir = Path(store_dir).resolve()
        self.objects_dir = self.base_dir / "objects"
        self.objects_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, hash_: str) -> tuple[Path, str]:
        raw_hex = hash_.removeprefix("sha256:").lower()
        if len(raw_hex) != 64:
            raise IntegrityError(f"Invalid SHA-256 object hash: {hash_!r}")
        shard = raw_hex[:2]
        rest = raw_hex[2:]
        return self.objects_dir / shard / rest, f"sha256:{raw_hex}"

    def put(self, data: bytes) -> str:
        """
        Write bytes atomically to the content-addressed object store.

        Returns canonical hash string: sha256:<hex>.
        """
        digest = hashlib.sha256(data).hexdigest()
        hash_ = f"sha256:{digest}"
        target_path, _ = self._resolve_path(hash_)

        if target_path.is_file():
            return hash_

        shard_dir = target_path.parent
        shard_dir.mkdir(parents=True, exist_ok=True)

        temp_name = f".tmp_{secrets.token_hex(8)}"
        temp_path = shard_dir / temp_name

        fd = os.open(
            str(temp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with open(fd, "wb", closefd=False) as f:
                f.write(data)
                f.flush()
                os.fsync(fd)
        finally:
            os.close(fd)

        os.replace(temp_path, target_path)

        # On POSIX, fsync the containing directory to guarantee directory entry persistence
        if hasattr(os, "O_DIRECTORY") and sys.platform != "win32":
            try:
                dir_fd = os.open(str(shard_dir), os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # Directory fsync is advisory; ignore filesystems that do not support it
                pass

        return hash_

    def get(self, hash_: str) -> bytes:
        """Retrieve stored object bytes by content hash."""
        target_path, _ = self._resolve_path(hash_)
        if not target_path.is_file():
            raise FileNotFoundError(f"Object not found in store: {hash_}")
        return target_path.read_bytes()

    def exists(self, hash_: str) -> bool:
        """Check whether object exists in store."""
        target_path, _ = self._resolve_path(hash_)
        return target_path.is_file()
