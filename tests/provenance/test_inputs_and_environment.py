from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from numericos import __version__
from numericos.core.experiment import InputSpec
from numericos.provenance import environment
from numericos.provenance.executable import resolve_executable
from numericos.provenance.inputs import InputError, checksum_inputs


def write(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_inputs_are_hashed_under_the_base_they_declare(tmp_path: Path) -> None:
    code_dir, project = tmp_path / "code", tmp_path / "project"
    mesh = write(code_dir / "meshes/grid-128.msh", b"mesh")
    field = write(project / "data/initial.npy", b"\x00" * 4096)

    records = checksum_inputs(
        [
            InputSpec(path="meshes/grid-128.msh", sha256=mesh),
            InputSpec(path="data/initial.npy", base="project"),
        ],
        code_dir=code_dir,
        project_root=project,
    )

    assert [(r.path, r.base, r.sha256, r.size_bytes) for r in records] == [
        ("meshes/grid-128.msh", "code", mesh, 4),
        ("data/initial.npy", "project", field, 4096),
    ]


def test_a_missing_changed_or_escaping_input_stops_the_launch(tmp_path: Path) -> None:
    code_dir, project = tmp_path / "code", tmp_path / "project"
    write(code_dir / "mesh.msh", b"another mesh")
    write(tmp_path / "secret.txt", b"outside")
    (code_dir / "link.txt").symlink_to(tmp_path / "secret.txt")
    project.mkdir()

    def check(spec: InputSpec) -> None:
        checksum_inputs([spec], code_dir=code_dir, project_root=project)

    with pytest.raises(InputError, match="was not found"):
        check(InputSpec(path="absent.msh"))
    with pytest.raises(InputError, match="the protocol expects"):
        check(InputSpec(path="mesh.msh", sha256="0" * 64))
    with pytest.raises(InputError, match="leads outside"):
        check(InputSpec(path="link.txt"))


def test_host_facts_describe_this_machine() -> None:
    facts = environment.host_facts()

    assert facts.numericos == __version__
    assert facts.python == ".".join(map(str, sys.version_info[:3]))
    assert facts.memory_total_bytes > 0
    assert facts.cpu_count_logical is None or facts.cpu_count_logical >= 1
    assert facts.processor and facts.platform and facts.machine and facts.hostname


def test_a_run_gets_only_the_environment_the_protocol_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("UNRELATED_TOKEN", "do-not-leak")
    monkeypatch.setenv("SOLVER_LICENSE_KEY", "k-123")

    env = environment.run_environment(
        declared={"MKL_NUM_THREADS": "1"},
        inherit=["OMP_NUM_THREADS", "SOLVER_LICENSE_KEY", "NOT_SET_ANYWHERE"],
        extra={"NUMERICOS_RUN_ID": "run_1"},
    )

    assert env["PATH"] == "/usr/bin:/bin"
    assert env["OMP_NUM_THREADS"] == "8"
    assert env["MKL_NUM_THREADS"] == "1"
    assert env["NUMERICOS_RUN_ID"] == "run_1"
    assert "UNRELATED_TOKEN" not in env
    assert "NOT_SET_ANYWHERE" not in env
    assert env["SOLVER_LICENSE_KEY"] == "k-123"  # the run gets the value...
    stored = environment.redact(env)
    assert stored["SOLVER_LICENSE_KEY"] == environment.REDACTED  # ...the record does not
    assert stored["OMP_NUM_THREADS"] == "8"


def test_the_program_file_is_resolved_and_digested(tmp_path: Path) -> None:
    tool = tmp_path / "bin" / "solve"
    digest = write(tool, b"#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    env = {"PATH": str(tool.parent)}

    on_path = resolve_executable("solve", env, tmp_path)
    relative = resolve_executable("bin/solve", env, tmp_path)
    missing = resolve_executable("no-such-solver", env, tmp_path)

    assert (on_path.path, on_path.sha256, on_path.size_bytes) == (str(tool.resolve()), digest, 17)
    assert relative.path == str(tool.resolve())
    assert (missing.argv0, missing.path, missing.sha256) == ("no-such-solver", None, None)


def test_probes_record_what_they_print_and_what_went_wrong(tmp_path: Path) -> None:
    env = {"PATH": "/usr/bin:/bin"}
    commands = [
        [sys.executable, "-c", "print('solver 1.2.3')"],
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        ["no-such-probe-command"],
    ]

    ok, failed, absent = environment.run_probes(
        commands, cwd=tmp_path, environment=env, output_dir=tmp_path / "environment"
    )

    assert ok.exit_code == 0
    assert ok.output_file == "probe-00.txt"
    assert (tmp_path / "environment" / "probe-00.txt").read_text() == "solver 1.2.3\n"
    assert ok.output_sha256 == hashlib.sha256(b"solver 1.2.3\n").hexdigest()
    assert failed.exit_code == 3
    assert (absent.exit_code, absent.output_file) == (None, None)
    assert absent.error is not None and "FileNotFoundError" in absent.error


def test_a_run_does_not_inherit_the_environment_numericos_itself_runs_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The tests run inside a virtual environment, as a supervisor started with `uv run` does.
    assert sys.prefix != sys.base_prefix
    own = f"{sys.prefix}/bin"
    monkeypatch.setenv("PATH", f"{own}:/usr/local/bin:/usr/bin:/bin")

    inherited = environment.run_environment({}, [], {})
    declared = environment.run_environment({"PATH": f"{own}:/opt/solver/bin"}, [], {})

    assert inherited["PATH"] == "/usr/local/bin:/usr/bin:/bin"
    assert declared["PATH"] == f"{own}:/opt/solver/bin"  # what the protocol says is kept
    assert "VIRTUAL_ENV" not in inherited


def test_outside_a_virtual_environment_the_path_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)

    assert environment.without_own_environment("/a/bin:/b/bin") == "/a/bin:/b/bin"
