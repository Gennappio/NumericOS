"""The files of a finished run, with size and checksum."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

from numericos.core.digests import file_digest
from numericos.executor import layout
from numericos.provenance import code

MAX_RESULT_FILES = 1000
MAX_HASHED_BYTES = 2 * 1024 * 1024 * 1024
#: Caches and environments that tools create as a side effect of running: never a result.
IGNORED_DIRECTORIES = frozenset(
    {
        "__pycache__",
        ".venv",
        "node_modules",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ipynb_checkpoints",
    }
)

_FIXED = (
    (layout.OUTPUT, "output", "application/x-ndjson"),
    (layout.RESOURCES, "resources", "application/x-ndjson"),
    (layout.JOURNAL, "journal", "application/x-ndjson"),
    (layout.EXIT, "outcome", "application/json"),
    (layout.METRICS_SUMMARY, "metric_summary", "application/json"),
    (layout.MONITOR_LOG, "monitor_log", "text/plain"),
    (code.DIFF_FILE, "code_diff", "text/x-diff"),
    (code.UNTRACKED_ARCHIVE, "untracked_files", "application/x-tar"),
)


@dataclass(frozen=True)
class Found:
    kind: str
    name: str
    media_type: str
    size_bytes: int
    sha256: str | None


def _found(run_dir: Path, path: Path, kind: str, media_type: str) -> Found:
    size = path.stat().st_size
    sha256 = file_digest(path)[0] if size <= MAX_HASHED_BYTES else None
    return Found(kind, path.relative_to(run_dir).as_posix(), media_type, size, sha256)


def _files_under(root: Path) -> list[Path]:
    """Regular files below ``root`` in a stable order. Links are neither listed nor followed."""
    files = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in IGNORED_DIRECTORIES)
        here = Path(directory)
        files += [
            path
            for path in (here / name for name in sorted(filenames))
            if path.is_file() and not path.is_symlink()
        ]
    return files


def _written_by_the_program(run_dir: Path) -> list[Path]:
    """Files in the exported code that the program created or changed.

    Many programs write next to their sources. The monitor touches a stamp just before it
    starts the program; the commit's own files and whatever the build produced are older
    than the stamp, what the program wrote is not.
    """
    code_dir, stamp = run_dir / layout.CODE, run_dir / layout.LAUNCH
    if not code_dir.is_dir() or not stamp.exists():
        return []
    launched = stamp.stat().st_mtime_ns
    return [path for path in _files_under(code_dir) if path.stat().st_mtime_ns >= launched]


def collect(run_dir: Path) -> tuple[list[Found], int]:
    """What the run left: the monitor's records (with the samples of every metric),
    provenance files and the program's results.

    Results are the files under ``outputs/`` and, for a run of an exported commit, the files
    the program wrote into its code directory. At most ``MAX_RESULT_FILES`` are listed; the
    second value says how many were left out, so the list never looks complete when it is
    not. A run in the working tree writes into the project's own directory, which is not
    searched: only what it puts under ``outputs/`` is listed.
    """
    found = [
        _found(run_dir, run_dir / name, kind, media_type)
        for name, kind, media_type in _FIXED
        if (run_dir / name).is_file() and (run_dir / name).stat().st_size > 0
    ]
    for directory, kind, media_type in (
        (layout.ENVIRONMENT, "environment_probe", "text/plain"),
        (layout.METRICS, "metric_series", "application/x-ndjson"),
    ):
        if (run_dir / directory).is_dir():
            found += [
                _found(run_dir, path, kind, media_type)
                for path in sorted((run_dir / directory).iterdir())
                if path.is_file()
            ]
    outputs = run_dir / layout.OUTPUTS
    results = (_files_under(outputs) if outputs.is_dir() else []) + _written_by_the_program(run_dir)
    for path in results[:MAX_RESULT_FILES]:
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        found.append(_found(run_dir, path, "result", media_type))
    return found, max(0, len(results) - MAX_RESULT_FILES)
