"""Checksums of files. Standard library only: the per-run monitor uses it too."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_digest(path: Path) -> tuple[str, int]:
    """SHA-256 and size of a file, read in chunks."""
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
