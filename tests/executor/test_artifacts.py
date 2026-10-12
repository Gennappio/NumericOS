"""Which files of a run directory are registered as its artifacts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from numericos.executor import artifacts, layout


def test_records_provenance_files_probes_and_results_are_found(tmp_path: Path) -> None:
    (tmp_path / layout.OUTPUT).write_text('{"l":"x"}\n')
    (tmp_path / layout.EXIT).write_text("{}")
    (tmp_path / layout.JOURNAL).write_text("")  # an empty record is not an artifact
    (tmp_path / "code.diff").write_text("diff --git a/x b/x\n")
    (tmp_path / layout.ENVIRONMENT).mkdir()
    (tmp_path / layout.ENVIRONMENT / "probe-00.txt").write_text("gcc 14\n")
    (tmp_path / layout.SPEC).write_text('{"env": {"TOKEN": "secret"}}')  # never an artifact
    results = tmp_path / layout.OUTPUTS
    (results / "fields").mkdir(parents=True)
    (results / "fields" / "u.npy").write_bytes(b"\x93NUMPY")
    (results / "summary.json").write_text("{}")
    (results / "outside").symlink_to("/etc/hosts")

    found, left_out = artifacts.collect(tmp_path)

    by_name = {item.name: item for item in found}
    assert left_out == 0
    assert {name: item.kind for name, item in by_name.items()} == {
        "output.jsonl": "output",
        "exit.json": "outcome",
        "code.diff": "code_diff",
        "environment/probe-00.txt": "environment_probe",
        "outputs/fields/u.npy": "result",
        "outputs/summary.json": "result",
    }
    assert by_name["outputs/summary.json"].media_type == "application/json"
    assert by_name["outputs/fields/u.npy"].media_type == "application/octet-stream"
    assert by_name["outputs/fields/u.npy"].sha256 == hashlib.sha256(b"\x93NUMPY").hexdigest()
    assert by_name["outputs/fields/u.npy"].size_bytes == 6


def test_a_run_with_very_many_results_says_how_many_are_not_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts, "MAX_RESULT_FILES", 3)
    results = tmp_path / layout.OUTPUTS
    results.mkdir()
    for index in range(5):
        (results / f"step-{index}.txt").write_text(str(index))

    found, left_out = artifacts.collect(tmp_path)

    assert [item.name for item in found] == [f"outputs/step-{index}.txt" for index in range(3)]
    assert left_out == 2


def test_a_file_too_large_to_hash_is_listed_without_a_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts, "MAX_HASHED_BYTES", 4)
    results = tmp_path / layout.OUTPUTS
    results.mkdir()
    (results / "big.bin").write_bytes(b"12345")
    (results / "small.bin").write_bytes(b"1234")

    found, _left_out = artifacts.collect(tmp_path)

    by_name = {item.name: item for item in found}
    assert (by_name["outputs/big.bin"].sha256, by_name["outputs/big.bin"].size_bytes) == (None, 5)
    assert by_name["outputs/small.bin"].sha256 == hashlib.sha256(b"1234").hexdigest()


def test_in_the_exported_code_only_what_the_program_wrote_is_a_result(tmp_path: Path) -> None:
    code = tmp_path / layout.CODE
    (code / "src" / "__pycache__").mkdir(parents=True)
    (code / "src" / "solver.py").write_text("print(1)")
    (code / "build.o").write_text("object code")
    (code / "log.txt").write_text("committed")
    for early in code.rglob("*"):
        os.utime(early, ns=(1_000_000_000, 1_000_000_000))
    stamp = tmp_path / layout.LAUNCH
    stamp.touch()
    os.utime(stamp, ns=(2_000_000_000, 2_000_000_000))
    (code / "field.npy").write_bytes(b"data")  # created by the program
    (code / "log.txt").write_text("committed, then appended to")  # changed by the program
    (code / "src" / "__pycache__" / "solver.cpython-312.pyc").write_bytes(b"cache")
    (code / ".venv" / "bin").mkdir(parents=True)  # an environment a launcher created on the fly
    (code / ".venv" / "bin" / "python").write_bytes(b"interpreter")

    found, left_out = artifacts.collect(tmp_path)

    assert left_out == 0
    assert {item.name: item.kind for item in found} == {
        "code/field.npy": "result",
        "code/log.txt": "result",
    }


def test_without_a_launch_stamp_nothing_in_the_code_is_a_result(tmp_path: Path) -> None:
    code = tmp_path / layout.CODE
    code.mkdir()
    (code / "solver.py").write_text("print(1)")  # exported, but the program never started

    found, _left_out = artifacts.collect(tmp_path)

    assert found == []
