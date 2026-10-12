"""The environment of a run: the host, the program file, probe outputs and variables."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import psutil

from numericos import __version__
from numericos.core.provenance import ExecutableRecord, HostFacts, ProbeRecord
from numericos.provenance.code import file_digest

PROBE_TIMEOUT_SECONDS = 30
MAX_EXECUTABLE_HASH_BYTES = 512 * 1024 * 1024

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


def run_environment(
    declared: dict[str, str], inherit: list[str], extra: dict[str, str]
) -> dict[str, str]:
    """The complete environment of a run: a small base, the names the protocol asks to inherit,
    the values it declares, and the variables NumericOS adds. Nothing else leaks in."""
    environment = {
        name: os.environ[name] for name in (*BASE_ENVIRONMENT, *inherit) if name in os.environ
    }
    environment.update(declared)
    environment.update(extra)
    return environment


def redact(environment: dict[str, str]) -> dict[str, str]:
    """The environment as it may be stored: values of secret-looking names are replaced."""
    return {
        name: REDACTED if _SECRET_NAME.search(name) else value
        for name, value in sorted(environment.items())
    }


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
