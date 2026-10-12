"""A real Git repository for tests, isolated from the developer's own Git configuration."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ENVIRONMENT = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Ada Lovelace",
    "GIT_AUTHOR_EMAIL": "ada@example.invalid",
    "GIT_COMMITTER_NAME": "Ada Lovelace",
    "GIT_COMMITTER_EMAIL": "ada@example.invalid",
}

SOLVER = '''"""A stand-in for a solver: prints its arguments."""
import sys

print("solver", *sys.argv[1:])
'''


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.root), *args],
            env=ENVIRONMENT,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def write(self, relative: str, content: str, *, executable: bool = False) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if executable:
            path.chmod(0o755)
        return path

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.head

    @property
    def head(self) -> str:
        return self.git("rev-parse", "HEAD")


def make_repo(root: Path) -> Repo:
    """A repository with one commit: a solver script and a .gitignore."""
    root.mkdir(parents=True)
    repo = Repo(root)
    repo.git("init", "-q", "-b", "main")
    repo.write("examples/heat2d-python/heat2d.py", SOLVER)
    repo.write(".gitignore", "ignored/\n*.log\n")
    repo.commit("baseline solver")
    return repo
