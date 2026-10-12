"""Experiment contracts as files: finding them in a project's repository and registering them.

A contract usually lives next to the code it runs. Finding and reading it only reads the
project directory; it executes nothing and needs no execution trust.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from numericos.core.errors import InvalidRequestError, NotAGitRepositoryError
from numericos.core.experiment import ExperimentProtocol, protocol_digest, relative_path
from numericos.core.schemas import (
    ContractFile,
    ContractFileList,
    ContractImport,
    ExperimentCreate,
    ExperimentOut,
)
from numericos.events.ledger import EventContext
from numericos.persistence.unit_of_work import UnitOfWork
from numericos.provenance import git
from numericos.services import experiments
from numericos.services.guards import require_project

SCHEMA_TAG = "numericos.experiment.v1"
MAX_CONTRACT_BYTES = 256 * 1024
#: How many YAML files of a repository are looked at when searching for contracts.
MAX_FILES_SCANNED = 2000


def _issue(field: str, message: str, kind: str) -> dict[str, Any]:
    return {"loc": ["body", field], "msg": message, "type": kind}


def _refuse(field: str, message: str, kind: str) -> InvalidRequestError:
    return InvalidRequestError(message, details={"errors": [_issue(field, message, kind)]})


def _document(text: str, field: str) -> dict[str, Any]:
    """The mapping a contract file contains, or a refusal that says what is wrong with it."""
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise _refuse(field, f"not valid YAML: {error}", "invalid_yaml") from error
    if not isinstance(document, dict):
        raise _refuse(field, "a contract file must contain a mapping", "invalid_contract")
    return document


def _split(document: dict[str, Any], fallback_name: str) -> tuple[str, str | None, dict[str, Any]]:
    """A contract file may carry the experiment's name and hypothesis next to the protocol."""
    protocol = {
        key: value for key, value in document.items() if key not in ("name", "hypothesis_id")
    }
    name = document.get("name")
    hypothesis_id = document.get("hypothesis_id")
    return (
        name if isinstance(name, str) and name else fallback_name,
        hypothesis_id if isinstance(hypothesis_id, str) else None,
        protocol,
    )


def _problems(error: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(part) for part in issue['loc']) or 'contract'}: {issue['msg']}"
        for issue in error.errors()
    ]


def _root(root_path: str | None) -> Path | None:
    """The project directory when it is the top of a Git work tree; None without a path."""
    if root_path is None:
        return None
    root = Path(root_path)
    if not git.is_toplevel(root):
        raise NotAGitRepositoryError(
            f"{root} is not the top directory of a Git work tree",
            details={"root_path": str(root)},
        )
    return root


def _read(root: Path, relative: str) -> str | None:
    """The text of a file inside the project directory, or None if it is not a small text file
    in there."""
    path = root / relative
    try:
        inside = path.resolve().is_relative_to(root.resolve())
        if not inside or not path.is_file() or path.stat().st_size > MAX_CONTRACT_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def discover(uow: UnitOfWork, project_id: str) -> ContractFileList:
    """Contract files in the project's repository: tracked or new, not ignored."""
    with uow:
        project = require_project(uow, project_id)
        root_path = project.root_path
        registered = {
            (experiment.name, experiment.protocol_digest): experiment.id
            for experiment in uow.experiments.list_for_project(project.id)
        }
    root = _root(root_path)
    if root is None:
        return ContractFileList(files=[], scanned=0, truncated=False)

    candidates = git.list_files(root, ["*.yaml", "*.yml"])
    found: list[ContractFile] = []
    for relative in candidates[:MAX_FILES_SCANNED]:
        text = _read(root, relative)
        if text is None or SCHEMA_TAG not in text:
            continue
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if not isinstance(document, dict) or document.get("schema") != SCHEMA_TAG:
            continue
        name, _hypothesis, protocol = _split(document, Path(relative).stem)
        question = protocol.get("question")
        entry = ContractFile(
            path=relative,
            name=name,
            question=question if isinstance(question, str) else "",
            valid=True,
            problems=[],
            experiment_id=None,
        )
        try:
            digest = protocol_digest(ExperimentProtocol.model_validate(protocol))
        except ValidationError as error:
            entry = entry.model_copy(update={"valid": False, "problems": _problems(error)})
        else:
            entry = entry.model_copy(update={"experiment_id": registered.get((name, digest))})
        found.append(entry)
    return ContractFileList(
        files=found,
        scanned=min(len(candidates), MAX_FILES_SCANNED),
        truncated=len(candidates) > MAX_FILES_SCANNED,
    )


def import_contract(
    uow: UnitOfWork, project_id: str, data: ContractImport, context: EventContext
) -> tuple[ExperimentOut, bool]:
    """Register the experiment of a contract given as text or as a file of the project."""
    if data.path is not None:
        with uow:
            root_path = require_project(uow, project_id).root_path
        root = _root(root_path)
        if root is None:
            raise _refuse("path", "the project has no code path to read files from", "no_root")
        try:
            relative = relative_path(data.path)
        except ValueError as error:
            raise _refuse("path", str(error), "invalid_path") from error
        text = _read(root, relative)
        if text is None:
            raise _refuse(
                "path",
                f"{relative!r} is not a text file of at most {MAX_CONTRACT_BYTES // 1024} KiB "
                "inside the project directory",
                "unreadable",
            )
        field, fallback = "path", Path(relative).stem
    else:
        assert data.text is not None
        text, field, fallback = data.text, "text", "experiment"

    name, hypothesis_id, protocol = _split(_document(text, field), fallback)
    try:
        body = ExperimentCreate.model_validate(
            {"name": name, "hypothesis_id": hypothesis_id, "protocol": protocol}
        )
    except ValidationError as error:
        issues = [
            {
                "loc": ["body", field, *issue["loc"]],
                "msg": issue["msg"],
                "type": issue["type"],
            }
            for issue in error.errors()
        ]
        raise InvalidRequestError(
            "the file is not a valid experiment contract", details={"errors": issues}
        ) from error
    return experiments.create_experiment(uow, project_id, body, context, reuse=data.reuse)
