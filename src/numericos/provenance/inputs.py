"""Checksums of the input files a run declares."""

from __future__ import annotations

from pathlib import Path

from numericos.core.digests import file_digest
from numericos.core.experiment import InputSpec
from numericos.core.provenance import InputRecord


class InputError(Exception):
    """A declared input is missing, outside its base directory, or not the expected file."""


def checksum_inputs(
    inputs: list[InputSpec], *, code_dir: Path, project_root: Path
) -> list[InputRecord]:
    """Hash every declared input; fail if one is missing or differs from its expected SHA-256."""
    records = []
    for spec in inputs:
        base = code_dir if spec.base == "code" else project_root
        path = base / spec.path
        if not path.resolve().is_relative_to(base.resolve()):
            raise InputError(f"input {spec.path!r} leads outside its {spec.base} directory")
        if not path.is_file():
            raise InputError(f"input {spec.path!r} was not found under the {spec.base} directory")
        sha256, size = file_digest(path)
        if spec.sha256 is not None and spec.sha256 != sha256:
            raise InputError(
                f"input {spec.path!r} has SHA-256 {sha256}, the protocol expects {spec.sha256}"
            )
        records.append(InputRecord(path=spec.path, base=spec.base, sha256=sha256, size_bytes=size))
    return records
