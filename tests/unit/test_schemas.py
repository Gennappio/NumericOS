from __future__ import annotations

import pytest
from pydantic import ValidationError

from numericos.core.enums import CardType, WorkflowStatus
from numericos.core.schemas import CardCreate, CardPatch, ProjectCreate, ProjectPatch


def test_unknown_fields_are_rejected_not_ignored() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ProjectCreate(name="x", status="planned")  # type: ignore[call-arg]


def test_project_root_path_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        ProjectCreate(name="x", root_path="relative/path")
    assert ProjectCreate(name="x", root_path="/tmp/solver").root_path == "/tmp/solver"


def test_project_patch_requires_a_version_and_tracks_explicit_nulls() -> None:
    with pytest.raises(ValidationError, match="version"):
        ProjectPatch(name="renamed")  # type: ignore[call-arg]
    patch = ProjectPatch(version=2, root_path=None)
    assert patch.model_fields_set == {"version", "root_path"}


def test_card_defaults_and_bounds() -> None:
    card = CardCreate(type=CardType.HYPOTHESIS, title="H01")
    assert card.workflow_status is WorkflowStatus.BACKLOG
    with pytest.raises(ValidationError):
        CardCreate(type=CardType.TASK, title="")
    with pytest.raises(ValidationError):
        CardPatch(version=1, position=-1)
