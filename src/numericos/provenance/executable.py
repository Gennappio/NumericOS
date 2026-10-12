"""Which file a command runs as. Kept light: the per-run monitor imports it."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from numericos.core.digests import file_digest
from numericos.core.provenance import ExecutableRecord

MAX_EXECUTABLE_HASH_BYTES = 512 * 1024 * 1024


def resolve_executable(argv0: str, environment: dict[str, str], cwd: Path) -> ExecutableRecord:
    """The file ``argv0`` will run as, found the way the system finds it, with its digest."""
    if os.sep in argv0:
        candidate: str | None = str((cwd / argv0).resolve()) if not os.path.isabs(argv0) else argv0
        if candidate is not None and not os.access(candidate, os.X_OK):
            candidate = None
    else:
        candidate = shutil.which(argv0, path=environment.get("PATH", os.defpath))
    if candidate is None:
        return ExecutableRecord(argv0=argv0, path=None)
    resolved = Path(candidate).resolve()
    size = resolved.stat().st_size
    sha256 = file_digest(resolved)[0] if size <= MAX_EXECUTABLE_HASH_BYTES else None
    return ExecutableRecord(argv0=argv0, path=str(resolved), sha256=sha256, size_bytes=size)
