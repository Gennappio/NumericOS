"""What can be said about a file of a project from its name alone."""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from numericos.core.enums import FileCategory

IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff", ".eps"}
CODE = {
    ".py", ".pyx", ".ipynb", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".f", ".f77",
    ".f90", ".f95", ".f03", ".for", ".jl", ".m", ".r", ".rs", ".go", ".java", ".scala", ".kt",
    ".js", ".jsx", ".ts", ".tsx", ".sh", ".bash", ".zsh", ".cmake", ".cu", ".cuh", ".sql",
    ".lua", ".pl", ".rb", ".swift", ".cs", ".edp", ".geo",
}  # fmt: skip
DATA = {
    ".csv", ".tsv", ".dat", ".h5", ".hdf5", ".nc", ".npy", ".npz", ".parquet", ".feather",
    ".xlsx", ".xls", ".mat", ".vtk", ".vtu", ".vtp", ".pvd", ".xdmf", ".msh", ".mesh", ".bin",
    ".pkl", ".pickle", ".fits", ".jsonl", ".out", ".res", ".log",
}  # fmt: skip
CONFIG = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".json", ".env", ".lock", ".in"}
DOCUMENTATION = {".md", ".rst", ".tex", ".txt", ".pdf", ".docx", ".bib", ".org", ".adoc"}
CODE_NAMES = {"makefile", "cmakelists.txt", "dockerfile", "snakefile", "justfile", "sconstruct"}
CONFIG_NAMES = {".gitignore", ".gitattributes", ".editorconfig", "requirements.txt"}
DOCUMENTATION_NAMES = {"readme", "license", "licence", "changelog", "authors", "notice"}

#: Images a browser shows and the agent can look at.
VIEWABLE_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def guess_category(path: str) -> FileCategory:
    """A first sorting by name. Whether data is read or written by the program cannot be told
    from a name: that is ``data`` until a description says more."""
    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(name).suffix
    if name in CODE_NAMES:
        return FileCategory.CODE
    if name in CONFIG_NAMES:
        return FileCategory.CONFIG
    if PurePosixPath(name).stem in DOCUMENTATION_NAMES:
        return FileCategory.DOCUMENTATION
    if suffix in IMAGE:
        return FileCategory.IMAGE
    if suffix in CODE:
        return FileCategory.CODE
    if suffix in DATA:
        return FileCategory.DATA
    if suffix in CONFIG:
        return FileCategory.CONFIG
    if suffix in DOCUMENTATION:
        return FileCategory.DOCUMENTATION
    return FileCategory.OTHER


def is_viewable_image(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in VIEWABLE_IMAGES


def media_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"
