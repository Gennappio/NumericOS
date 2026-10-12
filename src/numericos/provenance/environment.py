"""The environment of a run: the host, probe outputs and variables."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil

from numericos import __version__
from numericos.core.provenance import HostFacts, ProbeRecord

PROBE_TIMEOUT_SECONDS = 30

#: Always passed from the supervisor's environment to a run, when set.
BASE_ENVIRONMENT = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "SHELL")
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.IGNORECASE)
REDACTED = "<redacted>"


def _cpu_brand() -> str:
    if platform.system() == "Darwin":
        completed = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(errors="replace").splitlines():
            if line.lower().startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or "unknown"


def host_facts() -> HostFacts:
    return HostFacts(
        platform=platform.platform(),
        machine=platform.machine(),
        processor=_cpu_brand(),
        cpu_count_logical=psutil.cpu_count(logical=True),
        cpu_count_physical=psutil.cpu_count(logical=False),
        memory_total_bytes=psutil.virtual_memory().total,
        hostname=socket.gethostname(),
        python=platform.python_version(),
        numericos=__version__,
    )


def without_own_environment(path: str) -> str:
    """``PATH`` without the directory of the virtual environment NumericOS itself runs in.

    Started through ``uv run`` or from an activated environment, the supervisor has its own
    interpreter first on ``PATH``. A run that says ``python3`` must get the user's Python, not
    the interpreter and packages of the tool that supervises it.
    """
    if sys.prefix == sys.base_prefix:
        return path
    own = os.path.realpath(os.path.join(sys.prefix, "bin"))
    return os.pathsep.join(
        entry for entry in path.split(os.pathsep) if os.path.realpath(entry) != own
    )


def run_environment(
    declared: dict[str, str], inherit: list[str], extra: dict[str, str]
) -> dict[str, str]:
    """The complete environment of a run: a small base, the names the protocol asks to inherit,
    the values it declares, and the variables NumericOS adds. Nothing else leaks in."""
    environment = {
        name: os.environ[name] for name in (*BASE_ENVIRONMENT, *inherit) if name in os.environ
    }
    if "PATH" in environment:
        environment["PATH"] = without_own_environment(environment["PATH"])
    environment.update(declared)
    environment.update(extra)
    return environment


def redact(environment: dict[str, str]) -> dict[str, str]:
    """The environment as it may be stored: values of secret-looking names are replaced."""
    return {
        name: REDACTED if _SECRET_NAME.search(name) else value
        for name, value in sorted(environment.items())
    }


def run_probes(
    commands: list[list[str]], *, cwd: Path, environment: dict[str, str], output_dir: Path
) -> list[ProbeRecord]:
    """Run the protocol's environment probes and keep what they print.

    A probe that fails or cannot be started is recorded as such; it does not stop the run,
    because a missing fact about the environment is itself worth knowing.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, argv in enumerate(commands):
        started = time.monotonic()
        name = f"probe-{index:02d}.txt"
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=PROBE_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            records.append(
                ProbeRecord(
                    argv=argv,
                    exit_code=None,
                    seconds=round(time.monotonic() - started, 3),
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue
        (output_dir / name).write_bytes(completed.stdout)
        records.append(
            ProbeRecord(
                argv=argv,
                exit_code=completed.returncode,
                seconds=round(time.monotonic() - started, 3),
                output_sha256=hashlib.sha256(completed.stdout).hexdigest(),
                output_file=name,
            )
        )
    return records
