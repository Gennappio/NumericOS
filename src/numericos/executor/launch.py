"""Preparing a run for its monitor: the code it executes, its inputs, environment and spec."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from numericos.core.enums import FailureClass
from numericos.core.experiment import ExperimentProtocol
from numericos.core.provenance import (
    CodeProvenance,
    EnvironmentRecord,
    ExecutableRecord,
    InputRecord,
)
from numericos.executor import layout
from numericos.executor.spec import RunSpec
from numericos.provenance import code, git
from numericos.provenance.environment import host_facts, redact, run_environment, run_probes
from numericos.provenance.inputs import InputError, checksum_inputs

MB = 1024 * 1024


class LaunchError(Exception):
    """A run cannot be started. ``failure_class`` says what kind of problem it is."""

    def __init__(self, failure_class: FailureClass, reason: str) -> None:
        super().__init__(reason)
        self.failure_class = failure_class
        self.reason = reason


@dataclass(frozen=True)
class Prepared:
    code: CodeProvenance
    inputs: list[InputRecord]
    environment: EnvironmentRecord


def _clear(run_dir: Path) -> None:
    """Remove what an earlier attempt that never started its program left behind."""
    for path in (run_dir / layout.CODE, run_dir / layout.ENVIRONMENT, *run_dir.glob(".export-*")):
        shutil.rmtree(path, ignore_errors=True)
    for name in (layout.SPEC, code.DIFF_FILE, code.UNTRACKED_ARCHIVE):
        (run_dir / name).unlink(missing_ok=True)


def prepare(
    *,
    run_dir: Path,
    run_id: str,
    root: Path,
    protocol: ExperimentProtocol,
    argv: list[str],
    build: list[list[str]],
    record: CodeProvenance,
) -> Prepared:
    """Materialise everything the monitor needs and write its ``spec.json``.

    In ``ref`` mode the commit is exported into the run directory; in ``working_tree`` mode
    the tree is recorded as it is now and the program will run in place.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    _clear(run_dir)
    outputs = run_dir / layout.OUTPUTS
    outputs.mkdir(exist_ok=True)
    execution = protocol.execution

    try:
        if record.mode == "ref":
            if record.sha is None:
                raise LaunchError(FailureClass.INFRASTRUCTURE, "the run has no commit to execute")
            code_dir = run_dir / layout.CODE
            git.export(root, record.sha, code_dir)
            where = f"commit {record.sha[:12]}"
        else:
            code_dir = root
            record = code.capture_working_tree(root, record, run_dir)
            where = "the working tree"
    except git.GitError as error:
        raise LaunchError(
            FailureClass.INFRASTRUCTURE, f"the code could not be prepared: {error}"
        ) from error

    cwd = code_dir / execution.workdir
    if not cwd.is_dir():
        raise LaunchError(
            FailureClass.CODE_ERROR,
            f"the working directory {execution.workdir!r} does not exist in {where}",
        )
    environment = run_environment(
        declared={"PYTHONUNBUFFERED": "1", **execution.env},
        inherit=execution.inherit_env,
        extra={
            "NUMERICOS_RUN_ID": run_id,
            "NUMERICOS_RUN_DIR": str(run_dir),
            "NUMERICOS_OUTPUT_DIR": str(outputs),
            "NUMERICOS_CODE_DIR": str(code_dir),
            "NUMERICOS_PROJECT_ROOT": str(root),
        },
    )
    try:
        inputs = checksum_inputs(execution.inputs, code_dir=code_dir, project_root=root)
    except InputError as error:
        raise LaunchError(FailureClass.DATA_PROBLEM, str(error)) from error

    described = EnvironmentRecord(
        host=host_facts(),
        # Resolved by the monitor when the program starts: a build may create it only then.
        executable=ExecutableRecord(argv0=argv[0], path=None),
        probes=run_probes(
            execution.environment_probes,
            cwd=cwd,
            environment=environment,
            output_dir=run_dir / layout.ENVIRONMENT,
        ),
        variables=redact(environment),
    )
    limits = protocol.limits
    spec = RunSpec(
        run_id=run_id,
        argv=argv,
        cwd=str(cwd),
        env=environment,
        build=build,
        wall_seconds=limits.wall_seconds,
        max_rss_bytes=limits.max_rss_mb * MB if limits.max_rss_mb is not None else None,
        grace_seconds=limits.grace_seconds,
        max_output_bytes=limits.max_output_mb * MB,
        resource_interval_seconds=protocol.observability.resource_interval_seconds,
        metrics=protocol.metrics,
        parsers=protocol.observability.parsers,
        guardrails=protocol.guardrails,
        max_metrics_bytes=limits.max_metrics_mb * MB,
    )
    # 0600: the spec holds the real environment of the run, secrets included.
    layout.write_json_atomic(
        run_dir / layout.SPEC, spec.model_dump(mode="json", by_alias=True), mode=0o600
    )
    return Prepared(code=record, inputs=inputs, environment=described)


def spawn_monitor(run_dir: Path) -> subprocess.Popen[bytes]:
    """Start the monitor of a prepared run, detached: it must outlive this process."""
    with (run_dir / layout.MONITOR_LOG).open("ab") as log:
        return subprocess.Popen(
            [sys.executable, "-m", "numericos.executor.monitor", str(run_dir)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            cwd=run_dir,
            start_new_session=True,
        )
